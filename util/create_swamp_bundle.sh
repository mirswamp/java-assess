#! /bin/bash

if test $# -ne 1; then
    echo "need a destination directory as an argument"
    exit 1
fi

destdir="${1}/in-files"
if [ ! -d "${destdir}" ]; then
    mkdir -p "${destdir}"
fi

releasedir="$(pwd)/release"

cp ${releasedir}/in-files/* ${destdir}

(source $(pwd)/util/create_run_bundle.sh ${destdir})

function createpasswd() {
awk \
'function randint(n) {
     srand() 
return int(n * rand())
} 

BEGIN {
      print randint(10000)
}'
}

cat > ${destdir}/run-params.conf <<EOF 
SWAMP_USERNAME=$(whoami)
SWAMP_USERID=$(id -u ${SWAMP_USERNAME})
SWAMP_PASSWORD=$(createpasswd)
EOF
