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

CXX=g++
CXXFLAGS0 = -O3 -std=c++20
CXXFLAGS=$(CXXFLAGS0) $(DROOT)
ROOT_CONFIG ?= root-config
DMYROOT= -DMYROOT
ROOTLIBS     := $(shell $(ROOT_CONFIG) --libs)
ROOTINCLUDE  := -I$(shell $(ROOT_CONFIG) --incdir)

none: make_root_tree

all: make_root_tree

make_root_tree: $(my_objs) froot.co
	$(F77) $(LDFLAGS) -o make_root_tree $(my_objs) $(OTHERLIBS) froot.co $(ROOTLIBS) -lImt -lvdt -ltbb $(OTHERLIBS) $(CERNLIBS) -L/usr/lib64 -lstdc++

%.o: %.f
	$(FC) -c $(FFLAGS) $<

%.co: %.c
	$(CXX) -c $(CXXFLAGS) $(DMYROOT) $(ROOTINCLUDE) -o $@ $<

clean:
	$(RM) *.o *.co make_root_tree
