#!/bin/bash

DIR="$(dirname "$(realpath "$0")")"
COMPDIR="$(realpath $DIR/..)/src/ui"

for file in $DIR/*.ui; do
    name="$(basename $file .ui)"
    pyuic5 --import-from=... --resource-suffix="" $file -o $COMPDIR/$name.py
    done
