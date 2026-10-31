# nvcc 12.4 refuses gcc 14: g++-13 is the host compiler.
NVCC ?= nvcc
FLAGS = -std=c++17 -ccbin g++-13 -O3 -Iinclude
SRC = $(wildcard src/*.cu) $(wildcard src/*.cpp)
lib.o: $(SRC)
	$(NVCC) $(FLAGS) -c $(SRC) -odir build
