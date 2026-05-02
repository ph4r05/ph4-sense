##
# @file CMakeLists.txt
# @brief ph4_tuyaopen_esp32bridge - TuyaOpen app
#
# Build: from the tuyaopen root directory:
#   tos build --project <path-to-this-dir> --platform <your_platform>
#
# Or symlink/copy this dir into tuyaopen/apps/ and:
#   cd tuyaopen && tos build --app ph4_tuyaopen_esp32bridge --platform <your_platform>
#/

# APP_PATH
set(APP_PATH ${CMAKE_CURRENT_LIST_DIR})

# APP_NAME
get_filename_component(APP_NAME ${APP_PATH} NAME)

# APP_SRCS
aux_source_directory(${APP_PATH}/src APP_SRCS)

# APP_INC
set(APP_INC
    ${APP_PATH}/src
)

########################################
# Target Configure
########################################
add_library(${EXAMPLE_LIB})

target_sources(${EXAMPLE_LIB}
    PRIVATE
        ${APP_SRCS}
    )

target_include_directories(${EXAMPLE_LIB}
    PRIVATE
        ${APP_INC}
    )
