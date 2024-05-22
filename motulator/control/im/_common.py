"""Common control functions and classes for for induction machine drives."""

from types import SimpleNamespace
from dataclasses import dataclass, field, InitVar
import numpy as np
from motulator._helpers import wrap


# %%
@dataclass
class ModelPars:
    """
    Inverse-Γ model parameters of an induction machine.
    
    Parameters
    ----------
    R_s : float
        Stator resistance (Ω).
    R_R : float
        Rotor resistance (Ω).
    L_sgm : float
        Leakage inductance (H).
    L_M : float
        Magnetizing inductance (H).
    n_p : int
        Number of pole pairs.  
    J : float
        Moment of inertia (kgm²).  
    
    """
    R_s: float = None
    R_R: float = None
    L_sgm: float = None
    L_M: float = None
    n_p: int = None
    J: float = None


# %%
@dataclass
class ObserverPars:
    """
    Reduced-order flux observer parameters.

    Parameters
    ----------
    model_par : ModelPars
        Machine model parameters.
    T_s : float
        Sampling period (s).
    sensorless : bool
        If True, sensorless mode is used. 
    alpha_o : float, optional
        Observer bandwidth (rad/s). The default is 2*pi*40.
    k_o : callable, optional
        Observer gain as a function of the rotor angular speed. The default is 
        ``lambda w_m: (0.5*R_R/L_M + 0.2*abs(w_m))/(R_R/L_M - 1j*w_m)`` if
        `sensorless` else ``lambda w_m: 1 + 0.2*abs(w_m)/(R_R/L_M - 1j*w_m)``.

    Notes
    -----
    The pure voltage model corresponds to ``k_o = lambda w_m: 0``, resulting in 
    the marginally stable estimation-error dynamics. The current model is 
    obtained by setting ``k_o = lambda w_m: 1``. 
            
    """
    model_par: ModelPars
    T_s: float
    sensorless: bool
    gain: SimpleNamespace = field(init=False)
    alpha_o: InitVar[float] = 2*np.pi*40
    k_o: InitVar[callable] = None

    def __post_init__(self, alpha_o, k_o):
        alpha = self.model_par.R_R/self.model_par.L_M
        if self.sensorless:
            k_o = (
                lambda w_m: (.5*alpha + .2*np.abs(w_m))/
                (alpha - 1j*w_m)) if k_o is None else k_o
        else:
            k_o = (
                lambda w_m: 1 + .2*np.abs(w_m)/
                (alpha - 1j*w_m)) if k_o is None else k_o
        # Collect the gains
        self.gain = SimpleNamespace(alpha_o=alpha_o, k_o=k_o)


# %%
class Observer:
    """
    Reduced-order flux observer in estimated rotor flux coordinates.

    This class implements a reduced-order flux observer for induction machines.
    Both sensored and sensorless operation are supported. The observer 
    structure is similar to [#Hin2010]_. The observer operates in estimated 
    rotor flux coordinates. 
    
    Parameters
    ----------
    observer_par : ObserverPars
        Observer parameters.

    References
    ----------
    .. [#Hin2010] Hinkkanen, Harnefors, Luomi, "Reduced-order flux observers 
       with stator-resistance adaptation for speed-sensorless induction motor 
       drives," IEEE Trans. Power Electron., 2010, 
       https://doi.org/10.1109/TPEL.2009.2039650

    """

    def __init__(self, observer_par):
        self.par = observer_par.model_par
        self.sensorless = observer_par.sensorless
        self.T_s = observer_par.T_s
        self.gain = observer_par.gain
        # Initialize states
        self.state = SimpleNamespace(psi_R=0, theta_s=0, w_m=0)
        # Internal work variables for the update method
        self._work = SimpleNamespace(d_psi_R=0, d_w_m=0, old_i_s=0)

    def output(self, fbk):
        """         
        Compute the feedback signals for the control system.

        Parameters
        ----------
        fbk : SimpleNamespace
            Measured signals, which should contain the following fields:
            u_ss : complex
                Stator voltage (V) in stator coordinates.
            i_ss : complex
                Stator current (A) in stator coordinates.
            w_m : float, optional
                Rotor angular speed (electrical rad/s). This is only needed in 
                the sensored mode.

        Returns
        -------
        fbk : SimpleNamespace
            Measured and estimated feedback signals for the control system, 
            containing at least the following fields:
            u_s : complex
                Stator voltage (V) in estimated rotor flux coordinates.
            i_s : complex
                Stator current (A) in estimated rotor flux coordinates.
            psi_R : float
                Rotor flux magnitude estimate (Vs).
            theta_s : float
                Rotor flux angle estimate (rad).
            w_s : float
                Angular frequency (rad/s) of the coordinate system.
            w_m : float
                Rotor speed estimate (electrical rad/s).
            w_r : float
                Slip angular frequency (rad/s).
            psi_s : complex
                Stator flux estimate (Vs).
 
        """
        # Parameter estimates
        par = self.par

        # Get the rotor flux estimate
        fbk.psi_R, fbk.theta_s = self.state.psi_R, self.state.theta_s

        # Get the rotor speed estimate in the sensorless mode
        fbk.w_m = self.state.w_m if self.sensorless else fbk.w_m

        # Current and voltage vectors in estimated rotor flux coordinates
        fbk.i_s = np.exp(-1j*fbk.theta_s)*fbk.i_ss
        fbk.u_s = np.exp(-1j*fbk.theta_s)*fbk.u_ss

        # Stator flux estimate
        fbk.psi_s = par.L_sgm*fbk.i_s + fbk.psi_R

        # Induced voltage from the stator quantities (without the w_s term that
        # is taken into account separately to avoid an algebraic loop)
        d_i_s = (fbk.i_s - self._work.old_i_s)/self.T_s
        v_s = fbk.u_s - par.R_s*fbk.i_s - par.L_sgm*d_i_s

        # Induced voltage from the rotor quantities
        v_r = par.R_R*fbk.i_s - (par.R_R/par.L_M - 1j*fbk.w_m)*fbk.psi_R

        # Observer gains
        if self.sensorless:
            k_o1 = self.gain.k_o(fbk.w_m)
            k_o2 = k_o1
        else:
            k_o1, k_o2 = self.gain.k_o(fbk.w_m), 0

        # Angular frequencies
        den = fbk.psi_R + par.L_sgm*np.real(
            (1 - k_o1)*fbk.i_s + k_o2*np.conj(fbk.i_s))
        num = np.imag(v_s + k_o1*(v_r - v_s) + k_o2*np.conj(v_r - v_s))
        fbk.w_s = num/den if den > 0 else fbk.w_m
        fbk.w_r = par.R_R*fbk.i_s.imag/fbk.psi_R if fbk.psi_R > 0 else 0

        # Compute and store the derivatives for the update method
        v = v_s - 1j*fbk.w_s*par.L_sgm*fbk.i_s
        self._work.d_psi_R = np.real(
            v + k_o1*(v_r - v) + k_o2*np.conj(v_r - v))
        self._work.d_w_m = self.gain.alpha_o*(fbk.w_s - fbk.w_r - fbk.w_m)

        return fbk

    def update(self, T_s, fbk):
        """
        Update the states.

        Parameters
        ----------
        T_s : float
            Sampling period (s).
        fbk : SimpleNamespace
            Feedback signals.

        """
        # Update the states
        self.state.psi_R += T_s*self._work.d_psi_R
        self.state.theta_s = wrap(self.state.theta_s + T_s*fbk.w_s)
        self.state.w_m += T_s*self._work.d_w_m

        # Update the sampling period (needed in the output method)
        self.T_s = T_s

        # Store the old current
        self._work.old_i_s = fbk.i_s


# %%
@dataclass
class FullOrderObserverPars(ObserverPars):
    """
    Full-order observer parameters.

    Parameters
    ----------
    alpha_i : float, optional
        Current estimation bandwidth (rad/s). The default is 2*pi*400.

    """
    alpha_i: InitVar[float] = 2*np.pi*400

    def __post_init__(self, alpha_o, k_o, alpha_i):
        super().__post_init__(alpha_o, k_o)
        alpha = self.model_par.R_R/self.model_par.L_M
        self.gain.alpha_i = alpha_i if alpha_i is not None else self.alpha_i
        self.gain.g = alpha_i - alpha


# %%
class FullOrderObserver:
    """
    Full-order flux observer in estimated rotor flux coordinates.

    This class implements a full-order flux observer for induction machines. 
    The observer structure is similar to [#Tii2023]_. The observer operates in 
    estimated rotor flux coordinates. 
    
    Parameters
    ----------
    observer_par : ObserverPars
        Observer parameters.

    References
    ----------
    .. [#Tii2023] Tiitinen, Hinkkanen, Harnefors, "Speed-adaptive full-order 
       observer revisited: Closed-form design for induction motor drives," 
       Proc. IEEE SLED, 2023, https://doi.org/10.1109/SLED57582.2023.10261359

    """

    # pylint: disable=too-many-instance-attributes, too-many-arguments
    def __init__(self, observer_par):
        self.par = observer_par.model_par
        self.sensorless = observer_par.sensorless
        self.gain = observer_par.gain
        # Initialize states
        self.state = SimpleNamespace(psi_R=0, i_s=0, theta_s=0, w_m=0)
        # Internal work variables for the update method
        self._work = SimpleNamespace(d_psi_R=0, d_i_s=0, d_w_m=0)

        if not self.sensorless:
            raise NotImplementedError(
                "Sensored mode not implemented for this full-order observer")

    def output(self, fbk):
        """Output."""

        # Unpack
        par = self.par
        gain = self.gain
        par.R_sgm = par.R_s + par.R_R
        par.alpha = par.R_R/par.L_M

        # Get the estimates
        fbk.psi_R, fbk.theta_s = self.state.psi_R, self.state.theta_s
        fbk.w_m = self.state.w_m

        # Current and voltage vectors in estimated rotor flux coordinates
        fbk.i_s = np.exp(-1j*fbk.theta_s)*fbk.i_ss
        fbk.u_s = np.exp(-1j*fbk.theta_s)*fbk.u_ss

        # Stator flux estimate
        fbk.psi_s = par.L_sgm*self.state.i_s + fbk.psi_R

        # Current estimation error
        err_i_s = fbk.i_s - self.state.i_s

        # PI-type speed adaptation
        p_term = (
            -gain.alpha_o*par.L_sgm*err_i_s.imag/
            fbk.psi_R) if fbk.psi_R > 0 else 0
        w_m = p_term + self.state.w_m

        # Angular frequency of the rotor flux vector
        den = fbk.psi_R - par.L_sgm*err_i_s.real
        num = par.R_R*fbk.i_s.imag + par.L_sgm*(
            gain.alpha_i*gain.k_o(w_m).imag*err_i_s.real - gain.g*err_i_s.imag)
        fbk.w_s = w_m + num/den if den > 0 else w_m

        # Compute the derivatives
        k_i = par.L_sgm*(gain.g - 1j*(fbk.w_s - w_m)) - par.R_sgm
        self._work.d_i_s = (
            fbk.u_s - (par.R_sgm + 1j*fbk.w_s*par.L_sgm)*self.state.i_s +
            (par.alpha - 1j*w_m)*fbk.psi_R + k_i*err_i_s)/par.L_sgm
        self._work.d_psi_R = (
            -par.alpha*fbk.psi_R + par.R_R*fbk.i_s.real +
            (gain.alpha_i*gain.k_o(w_m).real - gain.g)*par.L_sgm*err_i_s.real -
            (fbk.w_s - w_m)*par.L_sgm*err_i_s.imag)

        # Derivative of the integral term of the speed estimate
        if fbk.psi_R > 0:
            self._work.d_w_m = (
                -gain.alpha_o*gain.alpha_i*par.L_sgm*err_i_s.imag/fbk.psi_R)
        else:
            self._work.d_w_m = 0

        return fbk

    def update(self, T_s, fbk):
        """
        Update the states.

        Parameters
        ----------
        T_s : float
            Sampling period (s).
        fbk : SimpleNamespace
            Feedback signals.

        """
        self.state.i_s += T_s*self._work.d_i_s
        self.state.psi_R += T_s*self._work.d_psi_R
        self.state.w_m += T_s*self._work.d_w_m
        self.state.theta_s = wrap(self.state.theta_s + T_s*fbk.w_s)
