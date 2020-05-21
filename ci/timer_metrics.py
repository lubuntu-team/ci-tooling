#!/usr/bin/env python3

# Copyright (C) 2020 Simon Quigley <tsimonq2@lubuntu.me>
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

import time
from tabulate import tabulate

tabulate.PRESERVE_WHITESPACE = True


class TimerMetrics:
    """Timer Metrics

    This leverages the timer module to provide a lightweight set of timer
    utilities, to keep track of how long specific sub-processes in a Python
    program are taking.

    Data structure:
    {
        "Timer name": {
            "running": True,
            "start_time": 123.4,
            "total_time": 0.0
        }
    }
    """

    def __init__(self):
        # Store the data in a dictionary
        self.data = {}

    def start(self, name):
        """Start a timer with a given name

        This records the current time and adds a new entry. If the entry
        already exists and the timer is not running, start it up again. If
        the entry exists and the timer is already running, do nothing.
        """

        # Get a timer value ASAP
        t_val = time.perf_counter()

        # If it isn't already there, create an entry
        if name not in self.data:
            # Initialize the entry
            self.data[name] = {}

            # Make sure it is running
            self.data[name]["running"] = True

            # Put our times in there
            self.data[name]["start_time"] = t_val
            self.data[name]["total_time"] = 0.0

        # If it is there, only act if it's running
        elif self.data[name]["running"] is False:
            # Now we're running
            self.data[name]["running"] = True

            # Change our start time as well
            self.data[name]["start_time"] = t_val

    def stop(self, name):
        """Stop a timer with the given name

        This stops the timer if it is running. If there is no such timer
        currently running, throw an error. If the timer exists and is running,
        stop it and update total_time. If the timer exists but isn't running,
        do nothing.
        """

        # Get a timer value ASAP
        t_val = time.perf_counter()

        # Raise an error if the timer doesn't exist
        if name not in self.data:
            assert ValueError("Timer " + name + " not found")

        # If the timer is running, update total_time and stop it
        if self.data[name]["running"] is True:
            # Stop the timer
            self.data[name]["running"] = False

            # Get the current time and add it to any existing time, which
            # may indeed exist
            cur_time = t_val - self.data[name]["start_time"]
            self.data[name]["total_time"] += cur_time

    def run(self, label):
        """Wrap a function inside a timer

        This allows for the usage of a decorator on a function which
        automatically and easily starts and ends a timer
        """
        self.start(label)

        def wrap(func):
            def run_function(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                finally:
                    self.stop(label)
            return run_function
        return wrap

    def display(self):
        """Print a pretty(-ish) table with all of the data in it"""

        # Initialize the dict for the table we're going to render
        # The dict keys are the headers
        table = {}

        # Simplify the data with just the times and the timer labels
        pretty = {}
        for item in self.data:
            pretty[item] = self.data[item]["total_time"]

        # Sort the data into descending order and then put them into two lists
        # Keys have one list and values have another
        s_pretty = {k: v for k,
                    v in sorted(pretty.items(),
                                key=lambda item: item[1],
                                reverse=True)}
        table["Timer"] = list(s_pretty.keys())
        table["Seconds"] = list(s_pretty.values())

        # Get a total second count
        total_secs = 0.0
        for i in range(len(table["Seconds"])):
            total_secs += table["Seconds"][i]

        # Add the totals to the table
        table["Timer"].append("Total Time")
        table["Seconds"].append(total_secs)

        # Get percentages in its own column
        table["% of total"] = []
        for i in range(len(table["Seconds"])):
            percent = (table["Seconds"][i] / total_secs) * 100.0
            # Round to the nearest hundredth and add a %
            table["% of total"].append(str(round(percent, 2)) + "%")

        # Show the pretty table
        print(tabulate(table, headers="keys", tablefmt="grid"))
