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
from os import getenv, path
from yaml import CLoader
from yaml import load as yaml_load
from jinja2 import Template
from shutil import rmtree
from tempfile import mkdtemp
from jenkinsapi.jenkins import Jenkins
from timer_metrics import TimerMetrics

timer = TimerMetrics()


class Generator:
    @timer.run("Clone the metadata")
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

            # Load all of the active config files and replace the given patch
            # with the data from those files
            active_configs = {}
            for conf in metadata_conf["active_configs"]:
                conf_path = path.join(metadata_loc, metadata_repo_name,
                                      conf)

                # Replace the string with a dict having all the data
                with open(conf_path) as conf_file:
                    conf_loaded = yaml_load(conf_file, Loader=CLoader)
                    active_configs[conf.replace(".conf", "")] = conf_loaded

            # Since metadata_conf["active_configs"] is a list, we have to use
            # a separate dict to store the new data until here
            metadata_conf["active_configs"] = active_configs
        finally:
            if metadata_loc:
                rmtree(metadata_loc)
            else:
                pass

        return metadata_conf

    @timer.run("Parse the metadata")
    def parse_metadata(self):
        """Parse the data pulled from clone_metadata

        Allow the user to be able to set default key values, resulting in
        shorter and cleaner configuration files.
        """

        mdata_conf = self.clone_metadata()
        mdata_req_keys = ["name", "packaging_url", "packaging_branch",
                          "upload_target", "releases", "default_branch",
                          "type", "upstream_url", "upstream_branch"]
        mdata_opt_keys = ["upstream_url", "upstream_branch"]
        mdata_sub_keys = {"NAME": "name"}

        for config in mdata_conf["active_configs"]:
            # Get the data, not just the key
            config = mdata_conf["active_configs"][config]

            # If the config is a merger job, don't bother with it
            if config["default"]["type"] == "merger":
                continue
            for package in config["repositories"]:
                # Load defaults in if they're not there, ignore the optionals 
                for mkey in mdata_req_keys:
                    if mkey not in package and mkey in config["default"]:
                        package[mkey] = config["default"][mkey]
                # Don't proceed if any of the keys in the config are invalid
                for mkey in package:
                    if mkey not in mdata_req_keys and mkey not in \
                       mdata_opt_keys:
                        raise ValueError("Invalid key present:", mkey)
                    # Substitute keys in
                    for skey in mdata_sub_keys:
                        if skey in package[mkey]:
                            nkey = package[mkey]
                            sub_key = package[mdata_sub_keys[skey]]
                            nkey = nkey.replace(skey, sub_key)
                            package[mkey] = nkey

        return mdata_conf

    @timer.run("Auth to Jenkins")
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

    @timer.run("Load configuration files")
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
            branch = data["packaging_branch"]
            upload_target = data["upload_target"]
        elif job_type != "release-mgmt":
            raise AttributeError("Data cannot be empty, cannot parse job data.")

        if job_type.startswith("package"):
            upstream = data["upstream_url"]
            package_config = template.render(PACKAGING_URL=url,
                                             PACKAGING_BRANCH=branch,
                                             UPSTREAM_URL=upstream,
                                             NAME=data["name"],
                                             RELEASE=data["release"],
                                             UPLOAD_TARGET=upload_target)
        elif job_type == "merger":
            # Cascading merges
            cascade = ""
            # Iterate on each value
            cascading = data["cascade"]
            for i in range(len(cascading)):
                # The default branch is first, we know this exists
                if i == 0:
                    cascade += "git checkout %s\n" % cascading[0]
                    continue
                c = cascading[i]
                # Create branch if it doesn't exist, check it out
                cascade += "git branch -a | egrep \"remotes/origin/"
                cascade += "%s\" &amp;&amp; git checkout %s || git " % (c, c)
                cascade += "checkout -b %s\n" % c
                # Fast-forward merge the previous branch in
                cascade += "git merge --ff-only %s\n" % cascading[i-1]
                # Push this branch
                cascade += "git push --set-upstream origin %s\n" % c

            package_config = template.render(PACKAGING_URL=url,
                                             MERGE_COMMANDS=cascade,
                                             NAME=data["name"])
        elif job_type == "release-mgmt":
            package_config = template.render()
        else:
            raise ValueError("Invalid job type")

        return package_config

    @timer.run("Create jobs and add to views")
    def create_jenkins_job(self, server, config, name, view):
        """This interacts with the Jenkins API to create the job"""

        print("Creating %s..." % name)

        if name in server.keys():
            job = server.get_job(name)
            job.update_config(config)
        else:
            job = server.create_job(name, str(config))
            if view in server.views:
                view = server.views[view]
            else:
                view = server.views.create(view)

            # Only add to the view if it's not already in there
            if not name in server.views[view]:
                view.add_job(name)

    @timer.run("Master function loop")
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
        print("Authenticated to Jenkins...")
        server = self.auth_jenkins_server()

        # Parse the metadata
        print("Parsing the metadata...")
        metadata = self.parse_metadata()

        total_rel = set()

        configs = {"merger": {}, "stable": {}, "unstable": {}}
        # Sort config names into different categories
        for config in metadata["active_configs"]:
            config_name = config
            config = metadata["active_configs"][config]
            for config_type in configs:
                if config["default"]["type"] == config_type:
                    configs[config_type][config_name] = metadata["active_configs"][config_name].copy()


        # Create the merger jobs first
        for config in configs["merger"]:
            config_name = config
            config = configs["merger"][config]
            parent = metadata["active_configs"][config["default"]["parent"]]
            for package in parent["repositories"]:
                if "cascade" not in package:
                    package["cascade"] = config["default"]["cascade"]
                name = config_name + "_" + package["name"]
                p_config = self.load_config("merger", package)
                self.create_jenkins_job(server, p_config, name, "merger")

        # Create the package jobs
        for job_type in ["stable", "unstable"]:
            # This is the actual loop
            for config in configs[job_type]:
                config_name = config
                config = configs[job_type][config]
                # Loop on the individual packages
                for package in config["repositories"]:
                    # Loop on each release
                    for release in package["releases"]:
                        # Add the release to the total release set, which is
                        # used to generate the management jobs
                        total_rel.add(release)

                        package["release"] = release
                        # Get the package config from the template
                        p_config = self.load_config("package-" + job_type,
                                                    package)
                        name = "%s_%s_%s" % (release, config_name,
                                             package["name"])
                        view_name = release + " " + job_type

                        # Actually create the job
                        self.create_jenkins_job(server, p_config, name,
                                                view_name)

        # From here on out, the same template is used
        p_config = self.load_config("release-mgmt")

        # Generate a management job for every release, stable and unstable
        for release in total_rel:
            for jobtype in ["stable", "unstable"]:
                job_name = "mgmt_build_" + release + "_" + jobtype
                self.create_jenkins_job(server, p_config, job_name, "mgmt")

        # Generate one last merger management job
        self.create_jenkins_job(server, p_config, "merger", "mgmt")



if __name__ == "__main__":
    generator = Generator()
    print(generator.create_jenkins_jobs())
    timer.display()
