#! /bin/bash

basedir=$(cd "$(dirname $(dirname "$0"))"; pwd)
cd ${basedir}

srcdir="${basedir}/src"
bindir="${basedir}/bin"

if [ ! -d "${bindir}" ]; then
    mkdir ${bindir}
fi

exe_name="java-assess"
exe_version="$(git tag | tail -n 1)"

(
    zip_file="${bindir}/${exe_name}.zip"
    
    (
	cd ${srcdir}
	cmd="zip -0 --recurse-paths ${zip_file} . --exclude '*~' --exclude '__pycache__"
	${cmd}
	echo "$(${cmd} --show-files --quiet)"
    )
    if [ -f "${zip_file}" ] && [ "${exe_version}" != "" ]; then
	ver="ver"
	mkdir ${ver}
	echo "${exe_version}" > "${ver}/version.txt"
	touch "${ver}/__init__.py"
	zip -0 --recurse-paths ${zip_file} ${ver} --quiet
	rm -rf ${ver}
    fi
)

(

    cd ${bindir}

    if [ -f ${exe_name} ]; then
	rm -rf ${exe_name}
    fi

    zip_file="${exe_name}.zip"
    if [ -f ${zip_file} ]; then
	echo '#!/usr/bin/env python3' | cat - ${zip_file} > ${exe_name} 
	chmod +x ${exe_name}
	rm -rf ${zip_file}
    else
	echo "${zip_file} not found"
    fi
)
