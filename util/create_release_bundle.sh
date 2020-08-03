#! /bin/bash

p=`basename $0`

## Create a java-assess release.
## Must be run from root directory of java-assess workspace.

make_tarball=true
make_cksum=true

p_swamp=/p/swamp

while [ $# -gt 0 ] ; do
	case $1 in
	--swamp-root)
		p_swamp=$2
		shift
		;;
	--no-tar)
		make_tarball=false
		;;
	--no-ck)
		make_cksum=false
		;;
	--test)
		make_tarball=false
		make_cksum=false
		;;
	-*)
		echo $p: $1: unkown optarg 1>&2
		exit 1
		;;
	*)
		break
		;;
	esac
	shift
done

if [ $# -lt 1  -o  $# -gt 2 ] ; then
	echo usage: $p dest-dir '[version]' 1>&2
	exit 1
fi


if false ; then
	## hack for vamshi's laptop environment
	if [ ! -d $p_swamp ] ; then
		p_swamp=$HOME/$p_swamp
		echo $p: adjusting /p/swamp for vamshi
	fi
fi

if [ -n "$SWAMP_FRAMEWORK_DEPENDENCIES" ]; then
	if [ ! -d "$SWAMP_FRAMEWORK_DEPENDENCIES" ]; then
		echo "$p: SWAMP_FRAMEWORK_DEPENDENCIES set, but not a directory ($SWAMP_FRAMEWORK_DEPENDENCIES)" 1>&2
		exit 1
	fi
	## SWAMP_FRAMEWORK_DEPENDENCIES overrides p_swamp & --swamp-root
	## XXX all uses of p_swamp should be removed
	## set p_swamp here, to prevent --swamp-root propagation
	p_swamp=/p/swamp
	p_swamp_fw=$SWAMP_FRAMEWORK_DEPENDENCIES
elif [ ! -d $p_swamp ] ; then
	echo $p: $p_swamp: swamp root dir missing 1>&2
	exit 1
else
	p_swamp_fw=${p_swamp}/frameworks
fi

update_platform=$p_swamp_fw/platform/update-platform

if [ ! -x $update_platform ] ; then
	echo $p: platform update tool missing/unusable 1>&2
	exit 1
fi




function md5_sum {

	local dest_dir="$1"

    (
		cd "$dest_dir"
		local checksumfile="md5sum"

		if test "$(uname -s)" == "Darwin"; then
			local MD5EXE="md5"
		elif test "$(uname -s)" == "Linux"; then
			local MD5EXE="md5sum"
		fi

		find . -type f ! -name "$checksumfile" -exec "$MD5EXE" '{}' ';' > "$checksumfile"
    )

}


version="${2:-$(git tag | sort -V | tail -n 1)}"
if [ $# -eq 1 ] ; then
	echo $p: $new_version: version from git
fi

vname=java-assess-$version
echo $p: $vname

## name it something instead of just using $1 all over the place
create_dir=$1

destdir="$create_dir/$vname/noarch"

if [ ! -d "${destdir}" ] ; then
	mkdir -p "${destdir}" || exit 1
fi

releasedir="$PWD/release"

if [ -d ${releasedir}/swamp-conf ] ; then
	cp -r ${releasedir}/swamp-conf ${destdir}
fi

cp -r ${releasedir}/in-files ${destdir}
s=${p_swamp_fw}/java/in-files
echo $p: $s: installing:
ls $s
## this was cp -r, but that copies symlinks instead of content; this issue
## happens across many swamp installers, should have a standard tool to use
cp -p $s/* ${destdir}/in-files
echo "$version" > "${destdir}/in-files/build_assess_driver_version.txt"

cp ${releasedir}/README.txt "$create_dir/$vname"
cp ${releasedir}/RELEASE_NOTES.txt "$create_dir/$vname"
cp ${releasedir}/LICENSE.txt "$create_dir/$vname"

echo $p: create run bundle
crb=./util/create_run_bundle.sh 
if [ "$p_swamp" != "/p/swamp" ] ; then
	crb="${crb} --swamp-root $p_swamp"
fi
$crb "${destdir}/in-files" "$version" || exit 1

## does it's own output
if [ "$p_swamp" != "/p/swamp" ] ; then
	update_platform="${update_platform} --swamp-root $p_swamp"
fi
$update_platform --framework java  --dir $destdir/in-files || exit 1

if $make_cksum ; then
	echo $p: checksums
	md5_sum $(dirname ${destdir})
fi

if $make_tarball ; then
	echo $p roll-up tarball
	## binary content in tar makes compression slow
	tar cf $create_dir/$vname.tar -C $create_dir $vname
fi
