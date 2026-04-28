      real*8 function sig_nuc_elastic(vertex)                                
                                                                        
C subroutine to calculate electron-nucleus electron scattering cross    
C section. Formulas from ASTRUC of Mo-Tsai program.                     
      IMPLICIT NONE
      real*8 QSQ,W1,W2,FF, THR
      real*8 CSMOTT, RECOIL,SI
      real*8 sigMott

      include 'simulate.inc'

      type(event):: vertex

      QSQ = vertex%Q2
      THR=vertex%e%theta
      CALL NUC_FORM_FACTOR(QSQ,W1,W2,FF,targ%Z,targ%A)                        

      CSMOTT = sigMott(vertex%e%E,vertex%e%theta,QSQ)
      RECOIL = targ%M/(targ%M+vertex%Ein*(1.-COS(THR)))                             
      sig_nuc_elastic  = (W2+2.*W1*TAN(THR/2.)**2)*CSMOTT*RECOIL                  

c      write(6,*) 'cheesy poofs ', W1,W2,CSMOTT,RECOIL,sig_nuc_elastic

      RETURN                                                            
      END   

*********************************************************************************
      SUBROUTINE NUC_FORM_FACTOR(QSQ,W1,W2,FF,Z,A)
!----------------------------------------------------------------------------
! Get Nuclear Form Factor from various models
!-----------------------------------------------------------

      IMPLICIT NONE
      REAL*8 QSQ,W1,W2,FF
      REAL*8 A, Z, FGAUSS

      W1=0.
      FF  = FGAUSS(QSQ,A) 
      W2  = (Z*FF)**2                                             


      RETURN
      END
!---------------------------------------------------------------------

      REAL*8 Function Fgauss(T,A)                                                
      IMPLICIT NONE                                                                             
      REAL*8 T, A, RADIUS,X2,CHAR
      include 'constants.inc'
                                                 
      Fgauss = 0.                                                       
      Radius = 1.07*A**(1./3.)  
! from H. de Vries: Nuclear Charge Density Distributions from Elastic Electron
!   Scattering. in Atomic Data and Nuclear Data Tables 36, 495(1987)
! 8/9/96
      IF(nint(A).EQ.205)RADIUS=5.470
      IF(nint(A).EQ.56) RADIUS=3.729    
      If(nint(A).EQ.28) RADIUS=3.085
      IF(nint(A).EQ.27) RADIUS=3.035                                                        
      x2     = (T/hbarc**2)*Radius**2                                 
      char   = (T/hbarc**2)*(2.4**2)/6.                               
      if (char.lt.80) Fgauss = exp(-char)/(1.+x2/6.)                    
      Return                                                            
      End                
