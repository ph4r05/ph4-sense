cmake_minimum_required(VERSION 3.16)

# Include Tuya IoT Core SDK before project() so it can register components
# The SDK is pulled via idf_component.yml or a git submodule in components/
# See README.md for setup instructions

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(ph4_tuya_esp32bridge)
