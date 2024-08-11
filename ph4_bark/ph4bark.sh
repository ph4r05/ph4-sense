#!/usr/bin/env sh
export LIBROSA_CACHE_DIR=/tmp/librosa_cache
export NUMBA_CACHE_DIR=/tmp
# export LIBROSA_CACHE_LEVEL=0
# mkdir -p LIBROSA_CACHE_DIR
exec python3.12 /usr/local/bin/ph4-bark $*
