#include "recon_hcana.C"

// Give the recon_hcana object a normal local lifetime. Invoking the class
// constructor directly as a ROOT macro expression leaves a temporary object
// in Cling until interpreter shutdown and can crash in its destructor on macOS.
void run_recon_hcana(TString filename,
                     TString reaction,
                     TString hadron_type = "mpi",
                     Bool_t electron_arm_hms = kTRUE) {
  recon_hcana reconstruction(filename, reaction, hadron_type, electron_arm_hms);
}
