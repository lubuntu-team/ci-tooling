#!/usr/bin/env python3

# Copyright (C) 2019 Simon Quigley <tsimonq2@lubuntu.me>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import git
import time
from os import getenv, path
from yaml import CLoader
from yaml import load as yaml_load
from jinja2 import Template
from shutil import rmtree
from tempfile import mkdtemp
from jenkinsapi.jenkins import Jenkins


class Generator:
    def clone_metadata(self):
        """Clone the metadata repository using the values set in the env vars

        The METADATA_URL and METADATA_REPO_NAME env vars must be set to use
        this function.

        The repository must have a ci.conf file in YAML format.

        This uses Git to clone the given repository - other VCSes are not
        supported at this time.
        """

        # Assuming this is ran inside Jenkins, this fetches the env vars set in
        # the job config. If those don't exist, we need to throw an error,
        # because otherwise we have no metadata to actually pull from
        metadata_url = getenv("METADATA_URL")
        metadata_repo_name = getenv("METADATA_REPO_NAME")
        if not metadata_url or not metadata_repo_name:
            raise ValueError("METADATA_URL and METADATA_REPO_NAME must be set")

        metadata_loc = None
        # Create a temporary directory in the most secure manner possible and
        # clone the metadata, throwing the directory away when we're done
        try:
            metadata_loc = mkdtemp()
            git.Git(metadata_loc).clone(metadata_url)

            # Load ci.conf and parse it
            config_file = path.join(metadata_loc,
                                    metadata_repo_name,
                                    "ci.conf")
            with open(config_file) as metadata_conf_file:
                metadata_conf = yaml_load(metadata_conf_file, Loader=CLoader)
        finally:
            if metadata_loc:
                rmtree(metadata_loc)
            else:
                pass

        return metadata_conf

    def parse_metadata(self):
        """Parse the data pulled from clone_metadata

        Allow the user to be able to set default key values, resulting in
        shorter and cleaner configuration files.
        """

        metadata_conf = self.clone_metadata()
        metadata_req_keys = ["name", "packaging_url",
                             "packaging_branch_unstable",
                             "packaging_branch_stable",
                             "upload_target_unstable", "upload_target_stable",
                             "releases", "default_branch"]
        metadata_opt_keys = ["upstream_url", "upstream_branch"]

        for package in metadata_conf["repositories"]:
            # Load defaults in if they're not there, ignore the optional ones
            for mkey in metadata_req_keys:
                if mkey not in package and mkey in metadata_conf["default"]:
                    package[mkey] = metadata_conf["default"][mkey]
            # Don't proceed if any of the keys in the config are invalid
            for mkey in package:
                if mkey not in metadata_req_keys and mkey not in \
                   metadata_opt_keys:
                    raise ValueError("Invalid key present:", mkey)

        return metadata_conf["repositories"]

    def auth_jenkins_server(self):
        """Authenticate to the Jenkins server

        This involves use of the API_SITE, API_USER, and API_KEY variables
        set in Jenkins. These need to be private, so they are defined in the
        system-wide Jenkins credential storage.
        """
        # Load the API values from the environment variables
        api_site = getenv("API_SITE")
        api_user = getenv("API_USER")
        api_key = getenv("API_KEY")
        for envvar in [api_site, api_user, api_key]:
            if not envvar:
                raise ValueError("API_SITE, API_USER, and API_KEY must be",
                                 "defined")
        # Authenticate to the server
        server = Jenkins(api_site, username=api_user, password=api_key)

        return server

    def load_config(self, job_type, data=None):
        """Return a template that is a result of loading the data

        This makes it easier to standardize several types of jobs
        """

        # The template name should always correspond with the job type
        # Regardless of the job type, there should always be a template
        template_path = path.join("templates",
                                  job_type + ".xml")
        with open(template_path) as templatef:
            template = ""
            for text in templatef.readlines():
                template += text
            template = Template(template)

        if data is not None:
            url = data["packaging_url"]
            u_branch = data["packaging_branch_unstable"]
            s_branch = data["packaging_branch_stable"]
            u_upload_target = data["upload_target_unstable"]
            s_upload_target = data["upload_target_stable"]
        elif job_type != "release-mgmt":
            raise AttributeError("Data cannot be empty, cannot parse job data.")

        if job_type.startswith("package"):
            upstream = data["upstream_url"]
            package_config = template.render(PACKAGING_URL=url,
                                             PACKAGING_BRANCH_U=u_branch,
                                             PACKAGING_BRANCH_S=s_branch,
                                             UPSTREAM_URL=upstream,
                                             NAME=data["name"],
                                             RELEASE=data["release"],
                                             UPLOAD_TARGET_U=u_upload_target,
                                             UPLOAD_TARGET_S=s_upload_target)
        elif job_type == "merger":
            default_branch = data["default_branch"]
            # HACKY HACKY HACKY
            # If we can't push to it, the merger job is useless
            if not "phab.lubuntu.me" in url:
                with open(path.join("templates", "useless-merger.xml")) as f:
                    package_config = ""
                    for text in f.readlines():
                        package_config += text
            else:
                package_config = template.render(PACKAGING_URL=url,
                                                 PACKAGING_BRANCH_U=u_branch,
                                                 PACKAGING_BRANCH_S=s_branch,
                                                 NAME=data["name"],
                                                 DEFAULT_BRANCH=default_branch)
        elif job_type == "release-mgmt":
            package_config = template.render()
        else:
            raise ValueError("Invalid job type")

        return package_config

    def get_existing_jenkins_jobs(self, server):
        """This returns a tuple of all existing Jenkins jobs

        This is separated into a different function to make the code slightly
        more efficient and clean. With generators being difficult to work with
        and the need for several high-volume variables, this makes sense.
        """

        # Start a timer
        t_start = time.perf_counter()
        print("Getting list of existing Jenkins jobs...")

        # Get the generator object with the jobs and create an empty list
        s_jobs = server.get_jobs()
        jobs = []

        # The list from the server is in the following format:
        # [('JOBNAME', <jenkinsapi.job.Job JOBNAME>)]
        # We only want JOBNAME, so let's put that in jobs
        for job_name in s_jobs:
            jobs.append(job_name[0])

        # Make sure jobs is a tuple
        jobs = tuple(jobs)

        # Stop the timer and log the time
        t_end = time.perf_counter()
        print(f"Finished in {t_end - t_start:0.4f} seconds.")

        return jobs

    def create_jenkins_jobs(self):
        """Interface with Jenkins to create the jobs required

        This uses the Jenkins API to do the following tasks:
         1. Assess which jobs are currently defined and if the jobs defined
            in the metadata overlap with those, do an update of the job config
            to match the current template.
         2. If there are new jobs defined, create them. If there are jobs no
            longer defined, remove them.
         3. Update the per-release views to ensure the jobs are in the correct
            views. If there are any releases no longer defined, remove them.
        """

        # Authenticate to the Jenkins server
        server = self.auth_jenkins_server()

        # Parse the metadata
        metadata = self.parse_metadata()

        # Get a list of existing jobs
        jobs = self.get_existing_jenkins_jobs(server)

        total_rel = set()

        for package in metadata:
            # Create the merger jobs first
            job_name = "merger_" + package["name"]
            package_config = self.load_config("merger", package)
            # TODO: This is duplicate code, and it should be consolidated
            if job_name in jobs:
                job = server.get_job(job_name)
                job.update_config(package_config)
            else:
                job = server.create_job(job_name, str(package_config))
                if "merger" in server.views:
                    view = server.views["merger"]
                else:
                    view = server.views.create("merger")
                view.add_job(job_name)

            for release in package["releases"]:
                # Add the release to the total release set, which is used to
                # generate the management jobs
                total_rel.add(release)

                # Load the config given the current data
                package["release"] = release
                for jobtype in ["unstable", "stable"]:
                    job_name = release + "_" + jobtype + "_" + package["name"]
                    package_config = self.load_config("package-" + jobtype,
                                                      package)
                    if job_name in jobs:
                        job = server.get_job(job_name)
                        job.update_config(str(package_config))
                    else:
                        job = server.create_job(job_name, str(package_config))

                    viewname = release + " " + jobtype
                    if viewname in server.views:
                        view = server.views[viewname]
                    else:
                        view = server.views.create(viewname)

                    view.add_job(job_name)

        # From here on out, the same template is used
        package_config = self.load_config("release-mgmt")

        # Generate a management job for every release, stable and unstable
        for release in total_rel:
            for jobtype in ["unstable", "stable"]:
                job_name = "mgmt_build_" + release + "_" + jobtype
                if job_name in jobs:
                    job = server.get_job(job_name)
                    job.update_config(package_config)
                else:
                    job = server.create_job(job_name, str(package_config))

                # The mgmt view should be the first view created, we don't
                # have to create it if it doesn't exist because that's a
                # Huge Problem anyway
                view = server.views["mgmt"]
                view.add_job(job_name)

        # Generate one last merger management job
        if "merger" in jobs:
            job = server.get_job("merger")
            job.update_config(package_config)
        else:
            job = server.create_job("merger", str(package_config))

        view = server.views["mgmt"]
        view.add_job("merger")


if __name__ == "__main__":
    generator = Generator()
    print(generator.create_jenkins_jobs())
