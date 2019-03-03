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
    def clone_repository(self):
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


if __name__ == "__main__":
    generator = Generator()
    generator.clone_repository()
