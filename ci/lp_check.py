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

import argparse
import launchpadlib
from time import sleep
from launchpadlib.launchpad import Launchpad


class LaunchpadCheck:
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--package", help="The source package",
                            required=True)
        parser.add_argument("-v", "--package-version", help="The package version",
                            required=True)
        parser.add_argument("-t", "--lp-team", help="Launchpad user with the PPA",
                            required=True)
        parser.add_argument("-r", "--ppa", help="Name of the Launchpad PPA",
                            required=True)
        args = parser.parse_args()
        self.lp_person = args.lp_team
        self.ppa_name = args.ppa
        self.verify_binaries_published(args.package, args.package_version)

    def login(self):
        """Log in to Launchpad anonymously"""
        lp = Launchpad.login_anonymously("CI Infrastructure", "production",
                                         version="devel")
        return lp

    def verify_source_published(self, package, package_version):
        """Verify that the source is published"""
        # Log in to Launchpad
        lp = self.login()

        # Grab the correct PPA object
        for ippa in lp.people[self.lp_person].ppas:
            if ippa.name == self.ppa_name:
                ppa = ippa

        # We're verifying every five minutes; never go to more than two hours
        # (60 minutes × 2 hours) ÷ 5 minutes = 24 max iterations
        for i in range(0, 24):
            print("Verifying if source is published,", (i*5), "minutes in.")
            ppa_source = ppa.getPublishedSources(source_name=package,
                                                 version=package_version,
                                                 order_by_date=True)[0]
            status = ppa_source.status
            # Error out if the package isn't on the way to becoming published
            if status != "Pending" and status != "Published":
                raise ValueError("Source package no longer exists")
            if status == "Published":
                print("Source published.")
                return lp, ppa
            elif status == "Pending":
                # 60 seconds × 5 minutes = 300 seconds
                sleep(300)
        # If we've timed out, raise an error
        raise ValueError("Timed out, contact Launchpad admins")

    def verify_binaries_published(self, package, package_version):
        """Verify that all of the binaries are published and have passed"""
        # Getting the source is a prerequisite
        lp, ppa = self.verify_source_published(package, package_version)

        # We're verifying every five minutes; never go to more than two hours
        # (60 minutes × 2 hours) ÷ 5 minutes = 24 max iterations
        for i in range(0, 24):
            print("Verifying if binaries are published,", (i*5), "minutes in.")
            need_sleep = False
            try:
                # Ensure all of the builds have passed or are in-progress
                for binary in ppa.getBuilds():
                    if binary.buildstate == "Needs building" or \
                       binary.buildstate == "Currently building" or \
                       binary.buildstate == "Uploading build":
                        print(binary.arch_tag, "still building.")
                        # Raise a one-way flag so the sleep isn't done during
                        # the iteration of the binaries
                        need_sleep = True
                    elif binary.buildstate == "Successfully built":
                        print(binary.arch_tag, "successfully built.")
                    else:
                        raise ValueError("One or more builds have an error")
                # Make sure all of the binaries are in a good state if they've
                # passed
                for binary in ppa.getPublishedBinaries():
                    if binary.status == "Pending":
                        print(binary_package_name, "still publishing.")
                        need_sleep = True
                    elif binary.status == "Published":
                        print(binary_package_name, "published.")
                    else:
                        raise ValueError("One or more builds can't publish")
            except IndexError:
                need_sleep = True

            if need_sleep:
                # 60 seconds × 5 minutes = 300 seconds
                sleep(300)
            else:
                print("All builds have successfully published.")
                break
        # If we've timed out, raise an error
        raise ValueError("Timed out, contact Launchpad admins")

if __name__ == "__main__":
    lpcheck = LaunchpadCheck()
