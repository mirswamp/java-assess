This document describes the input and output example files for a Java
assessment..


-------------------------------------
- run-params.conf
-------------------------------------
  An optional file that is used to determine the account information
  used to perform the build.  Three values can be set in this file, and
  the included example file create and does the work using
  user builder with uid 9999 and a password of "password for builder"


-------------------------------------
- run.conf
-------------------------------------
  File that describes the operation to be performed.  The supported
  values for 'goal' at this time are:
  
    build
    build+assess
    build+assess+parse
    assess
    assess+parse
    parse


-------------------------------------
- os-dependencies.conf
-------------------------------------
  Optional file containing the names of platform specific packages that
  are installed from the vendor's package repository.  There is one line
  per platform.  The included example file shows the values required for
  wireshark-1.10.2.


-------------------------------------
- package.conf
- <PACKAGE>.tar.gz
-------------------------------------
  required files that contain the source code of the package, along with
  parameters describing to build the package.


-------------------------------------
- tool.conf
- <tool-archive>.tar.gz
-------------------------------------
  The tool.conf describes the tool and its archive.


-------------------------------------
- build.conf
- <build-archive>.tar.gz
-------------------------------------
  The build.conf describes the package that has been built


-------------------------------------
- results.conf
- <results-archive>.tar.gz
-------------------------------------
  The results.conf describes the results and its archive.
  Required only if the goal is 'parse'.


-------------------------------------
- status.out
-------------------------------------
  file updated in the output directory with a dashboard of the progress.
  lines are added as tasks are completed, and are formatted as follows:
    
  <status>: <task> <extra-msg> <duration>
    ----------
    multiline-msg
    ----------

  <status>    alphanumeric value that start in column 1 and followed by a ':'
              current values are PASS, FAIL, NOTE, SKIP
  <task>      alphanumberic plus '-' and '_'
  <extra-msg> optional parenthesis surrounded characters without control
              character
  <duration>  optional decimal number of seconds followed by 's'

  multiline-msg's are deliminited by a line of 10 '-' characters, each line and
                  the delimiter and message lines are preceded by two spaces
		  the message is associated with the preceeding task
  
  If any of the status's are FAIL, the whole run should be considered failed.
