#!/bin/bash

function main {
    local  GIT_TAG="${1:-$(git tag | sort -V | tail -n 1)}"
    local FILENAME="release/RELEASE_NOTES.txt"

    if test -f "${FILENAME}"; then
	if test "$(uname -s)" == "Darwin"; then
	    MTIME="$(stat -f '%m' ${FILENAME})"
	elif  test "$(uname -s)" == "Linux"; then
	    MTIME="$(stat --format='%Y' ${FILENAME} )"
	fi
	
		# if test $# -gt 0; then
		# 	NEW_FILENAME="temp_release_notes.txt"
		# else
		# 	NEW_FILENAME="/dev/stdout"
		# fi
		#
	local NEW_FILENAME="temp_release_notes.txt"

	if test "$(git log --since=${MTIME} --pretty=fuller --format='%B')" != ""; then
	    SEP=$(python3 -c "print('-'*35)")
	    cat > "${NEW_FILENAME}" <<EOF
${SEP}
$(basename $PWD) version ${GIT_TAG} ($(date))
${SEP}
$(git log --since=${MTIME} --pretty=fuller --format='%B' | sed -r '/^[^-] .+/d' | sed -r 's:.+:- &:')

$(cat ${FILENAME})
EOF

if test "${NEW_FILENAME}" != "/dev/stdout" -a -f "${NEW_FILENAME}"; then
    mv "${NEW_FILENAME}" "${FILENAME}"
fi
	fi
    fi

}

#set -x

main "$@"
