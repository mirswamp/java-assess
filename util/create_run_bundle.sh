#!/bin/bash

p=`basename $0`

## where to find the frameworks content to be copied in
swamp=/p/swamp

## Due to positional args, special case for this, to avoid rewrite

case $1 in
--swamp-root)
	swamp=$2
	shift
	shift
	;;
esac

if [ ! -d "$swamp" ] ; then
	echo $p: swamp root missing 1>&2
	exit 1
fi

swamp_fw=${swamp}/frameworks
ivy_fw=${swamp_fw}/java/ivy/jars



## Create the "runnable" portion of java-assess.
## Script must be run from root directory of java-assess workspace.

if [ $# -lt 1 -o $# -gt 2 ] ; then
	echo usage: $p [--swamp-root dir]  dest-dir '[version]' 1>&2
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
#cp -r --no-dereference "${PWD}/build-sys" ${scriptsdir}
cp -r --no-dereference "${PWD}/bin" ${scriptsdir}

libdir="${scriptsdir}/lib"
mkdir -p $libdir || exit 1
cp -r ${PWD}/lib/* $libdir

## install the build systems from the frameworks directory
## We can install multiple versions, however, the "selected" version
## is always the default.
## XXX there is a naming issue, that ther is a coupling between
## the ivy versions here and in the source code which selects ivy
## this is a historical issue which is not yet fixed.  Please leave
## it alone for now; once ivy versions are configurable this will
## be fixed.

ivy_ver=2.3.0			## the version of ivy used
other_vers="2.4.0"		## other versions not defaults
other_vers=			## non for now
ivy_vers="$ivy_ver $other_vers"	## all the versions

bs_dir="${scriptsdir}/build-sys"
mkdir -p $bs_dir || exit 1
for ivy in $ivy_vers ; do
	ivy_vname=ivy-$ivy
	ivy_dir=$bs_dir/${ivy_vname}
	ivy_jar=${ivy_vname}.jar

	mkdir -p $ivy_dir || exit 1
	cp -p ${ivy_fw}/$ivy_jar $ivy_dir || exit 1

	## manufacture the symbolic links for the default version
	case $ivy in
	$ivy_ver)
		(cd $bs_dir ; rm -f ivy ; ln -s $ivy_vname ivy ) || exit 1
		;;
	esac

	## manufacture generic link to jar for all versions
	(cd $ivy_dir ; rm -f ivy.jar ; ln -s ${ivy_jar} ivy.jar ) || exit 1
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
