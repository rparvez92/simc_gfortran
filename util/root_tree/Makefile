## This makefile must be executed with gmake (gnu make).

## This tells make not to delete these target files on error/interrupt (see man page)
.PRECIOUS: *.o 
RM        = rm -f 
SHELL     = /bin/sh

OBJ	= make_root_tree.o
 
my_objs	=  $(OBJ)

my_deps = $(my_objs:.o=.d)

MYOS := $(subst -,,$(shell uname))

#For use with gfortran compiler
# -fno-automatic - all program storage treated as static
ifeq ($(MYOS),Linux)
  FFLAGSA=-
  INCLUDES=
  FFLAGS = -O3 -fno-automatic
  OTHERLIBS = 
  FC  := gfortran
  F77 := gfortran
endif

ifeq ($(MYOS),Darwin)
  FFLAGS = -O3 -fno-automatic
  OTHERLIBS =
  FC  := gfortran
  F77 := gfortran
endif

ROOT_CONFIG ?= root-config
CXX := $(shell $(ROOT_CONFIG) --cxx)
CXXFLAGS0 = -O3 -std=c++17
CXXFLAGS=$(CXXFLAGS0) $(DROOT)
DMYROOT= -DMYROOT
ROOTLIBS     := $(shell $(ROOT_CONFIG) --libs)
ROOTINCLUDE  := -I$(shell $(ROOT_CONFIG) --incdir)

ifeq ($(MYOS),Darwin)
  LINKER := $(CXX)
  FORTRAN_LIBDIR := $(dir $(shell $(FC) -print-file-name=libgfortran.dylib))
  FORTRAN_LIBS := -L$(FORTRAN_LIBDIR) -lgfortran -lquadmath
else
  LINKER := $(F77)
  FORTRAN_LIBS := -lstdc++
endif

none: make_root_tree

all: make_root_tree

make_root_tree: $(my_objs) froot.co
	$(LINKER) $(LDFLAGS) -o make_root_tree $(my_objs) froot.co $(ROOTLIBS) $(FORTRAN_LIBS) $(OTHERLIBS) $(CERNLIBS)

%.o: %.f
	$(FC) -c $(FFLAGS) $<

%.co: %.c
	$(CXX) -c $(CXXFLAGS) $(DMYROOT) $(ROOTINCLUDE) -o $@ $<

clean:
	$(RM) *.o *.co make_root_tree
