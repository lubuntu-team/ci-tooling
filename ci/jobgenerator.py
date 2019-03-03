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
from os import getenv
from yaml import CLoader
from yaml import load as yaml_load
from shutil import rmtree
from tempfile import mkdtemp

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
        if not metadata_url or metadata_url == "" or not metadata_repo_name \
            or metadata_repo_name == "":
            raise ValueError("METADATA_URL and METADATA_REPO_NAME must be set")

        # Create a temporary directory in the most secure manner possible and
        # clone the metadata, throwing the directory away when we're done
        try:
            metadata_loc = mkdtemp()
            git.Git(metadata_loc).clone(metadata_url)

            # Load ci.conf and parse it
            with open(metadata_loc + "/" + metadata_repo_name + "/ci.conf") \
                as metadata_conf_file:
                metadata_conf = yaml_load(metadata_conf_file, Loader=CLoader)
        finally:
            rmtree(metadata_loc)

        return metadata_conf

    def parse_metadata(self):
        """Parse the data pulled from clone_metadata

        Allow the user to be able to set default key values, resulting in
        shorter and cleaner configuration files.
        """

        metadata_conf = self.clone_metadata()
        metadata_req_keys = ["name", "packaging_url", "packaging_branch",
                             "upload_target", "releases"]
        metadata_opt_keys = ["upstream_url", "upstream_branch"]

        for package in metadata_conf["repositories"]:
            # Load defaults in if they're not there, ignore the optional ones
            for mkey in metadata_req_keys:
                if not mkey in package and mkey in metadata_conf["default"]:
                    package[mkey] = metadata_conf["default"][mkey]
            # Don't proceed if any of the keys in the config are invalid
            for mkey in package:
                if not mkey in metadata_req_keys and not mkey in \
                    metadata_opt_keys:
                    raise ValueError("Invalid key present:", mkey)

        return metadata_conf["repositories"]


if __name__ == "__main__":
    generator = Generator()
    print(generator.parse_metadata())
