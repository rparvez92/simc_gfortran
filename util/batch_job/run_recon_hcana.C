#include "recon_hcana.C"

// A void macro entry point gives the recon_hcana object ordinary block
// lifetime. Its destructor therefore runs before ROOT tears down TCling and
// ROOT's global TFile registry.
void run_recon_hcana(TString filename,
                     TString reaction_str,
                     TString hadron_type="mpi",
                     Bool_t Earm_HMS=kTRUE) {
  recon_hcana job(filename, reaction_str, hadron_type, Earm_HMS);
}
