This document describes the files that need to be placed in the virtual
machine's input directory to perform a build, or build and assessment of
a Java package:

From this release, the files included in the in-files directory need to
be placed in the VM's input directory

    - build_assess_driver
    - install-dependencies.sh
    - run.sh
    - scripts.tar.gz

In addition, the following files needs to be placed in the input directory:

    - run-params.conf
        Contains KEY=VALUE lines using Bash syntax (no spaces around equal
        sign and special characters need to quoted) where key is
            SWAMP_USERNAME
                username used to build, assess or parse
            SWAMP_USERID
                uid of username
            SWAMP_PASSWORD
                password of username
    - run.conf
        Contains the single line
            goal=<GOAL_TYPE>
        where <GOAL_TYPE> can have the following values:
            build
            build+assess
            build+assess+parse
            assess
            assess+parse
            parse

    - os-dependencies.conf
        Contains KEY=VALUE lines where the key contains the platform name,
        and the value is a space separated list of strings that name valid
        packages using the native package manager on the platform such as
            dependencies-<PLAT_NAME>=os-pkg1 os-pkg2 ...
        This file must contain the combined OS dependencies required by this
        software, the package, the assessment tool, and the parser.
