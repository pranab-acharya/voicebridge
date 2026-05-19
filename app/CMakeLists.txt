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
# FLOAT_APPROX must be set when any -ffast-math leaks through to opus sources
set(OPUS_FLOAT_APPROX    ON  CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(opus)

# lrint/lrintf exist in the NDK but cmake's check_function_exists misses them
# during cross-compilation, causing float_cast.h to emit a #warning fallback.
# Both are guaranteed on Android API 26+.
if(TARGET opus)
    target_compile_definitions(opus PRIVATE HAVE_LRINT=1 HAVE_LRINTF=1)
endif()

# Strip -ffast-math from opus targets — it refuses to build with it unless
# FLOAT_APPROX is also defined, which changes codec behaviour.
foreach(_t opus celt silk)
    if(TARGET ${_t})
        get_target_property(_opts ${_t} COMPILE_OPTIONS)
        if(_opts)
            list(REMOVE_ITEM _opts -ffast-math)
            set_target_properties(${_t} PROPERTIES COMPILE_OPTIONS "${_opts}")
        endif()
    endif()
endforeach()

add_library(voicebridge SHARED
    src/main/cpp/opus_jni.cpp
)

# Apply -ffast-math only to our own JNI target, not to opus
target_compile_options(voicebridge PRIVATE -ffast-math)

target_include_directories(voicebridge PRIVATE
    ${opus_SOURCE_DIR}/include
    src/main/cpp
)

target_link_libraries(voicebridge
    opus
    log
    android
)
