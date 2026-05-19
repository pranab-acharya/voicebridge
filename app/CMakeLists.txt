cmake_minimum_required(VERSION 3.22.1)
project(voicebridge C CXX)

include(FetchContent)

# Fetch libopus from GitHub (xiph mirror — reliable in CI)
FetchContent_Declare(
    opus
    GIT_REPOSITORY https://github.com/xiph/opus.git
    GIT_TAG        v1.3.1
    GIT_SHALLOW    TRUE
)

set(OPUS_BUILD_TESTING   OFF CACHE BOOL "" FORCE)
set(OPUS_BUILD_PROGRAMS  OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(opus)

add_library(voicebridge SHARED
    src/main/cpp/opus_jni.cpp
)

target_include_directories(voicebridge PRIVATE
    ${opus_SOURCE_DIR}/include
    src/main/cpp
)

target_link_libraries(voicebridge
    opus
    log
    android
)
