#!/bin/bash

p=`basename $0`

## Create the "runnable" portion of java-assess.
## Script must be run from root directory of java-assess workspace.

if [ $# -lt 1 -o $# -gt 2 ] ; then
    echo usage: $p dest-dir '[version]' 1>&2
    exit 1
fi

destdir="${1}"
if [ ! -d "${destdir}" ]; then
    mkdir -p "${destdir}" || exit 1
fi

version=$2

new_version="${2:-$(git tag | tail -n 1)}"

if [ $# -eq 1 ] ; then
    echo $p: $new_version: version from git
fi

scriptsdir="${destdir}/scripts"
mkdir -p "${scriptsdir}" || exit 1

cp -r --no-dereference "${PWD}/resources" ${scriptsdir}
cp -r --no-dereference "${PWD}/build-monitors" ${scriptsdir}
cp -r --no-dereference "${PWD}/build-sys" ${scriptsdir}
cp -r --no-dereference "${PWD}/bin" ${scriptsdir}

libdir="${scriptsdir}/lib"
mkdir -p $libdir || exit 1
cp -r ${PWD}/lib/* $libdir

## manufacture the symbolic links for the versions
bs_dir="$scriptsdir/build-sys"
for bs in ivy ;  do
    if [ ! -e "$bs_dir/$bs" ] ; then
	## this breaks if > 1 is there .. on purpose
	(cd ${bs_dir} ; ln -sf "${bs}"-* "${bs}" || echo XXX multiple $bs error )
    fi
done

java_assess_dir=${libdir}/java_assess
mkdir -p $java_assess_dir || exit 1
cp -r ${PWD}/src/* $java_assess_dir

version_dir="$libdir/version"
mkdir -p "$version_dir" || exit 1
echo "$new_version" > "$version_dir/version.txt"
: > "$version_dir/__init__.py"

cd "$(dirname ${scriptsdir})"
tar -c -z --file="$(basename ${scriptsdir})"".tar.gz" "$(basename ${scriptsdir})"
if [ $? -eq 0 ] ; then
    rm -rf "$(basename ${scriptsdir})"
else
    echo $p: archive creation failed 1>&2
fi
