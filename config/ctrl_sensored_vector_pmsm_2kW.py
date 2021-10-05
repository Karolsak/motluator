# pylint: disable=C0103
"""
This script configures sensorless vector control for a 2.2-kW permanent-magnet
synchronous motor drive.

"""
# %%
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from control.common import SpeedCtrl
from control.sm.vector import CurrentRef, CurrentCtrl2DOFPI
from control.sm.vector import VectorCtrl, Datalogger
from control.sm.opt_refs import OptimalLoci
from helpers import LUT, Sequence  # , Step
from config.mdl_pmsm_2kW import mdl


# %%
@dataclass
class BaseValues:
    """
    This data class contains the base values computed from the rated values.
    These are used for plotting the results.

    """
    # pylint: disable=too-many-instance-attributes
    w: float = 2*np.pi*75
    i: float = np.sqrt(2)*4.3
    u: float = np.sqrt(2/3)*370
    p: int = 3
    psi: float = u/w
    P: float = 1.5*u*i
    Z: float = u/i
    L: float = Z/w
    T: float = p*P/w


# %% Define the controller parameters
@dataclass
class CtrlParameters:
    """
    This data class contains parameters for the control system of a 2.2-kW
    permanent-magnet synchronous motor.

    """
    # pylint: disable=too-many-instance-attributes
    # Sampling period
    T_s: float = 250e-6
    # Bandwidths
    alpha_c: float = 2*np.pi*200
    alpha_fw: float = 2*np.pi*20
    alpha_s: float = 2*np.pi*4
    # Maximum values
    T_M_max: float = 2*14.6
    i_max: float = 1.5*np.sqrt(2)*5
    # Nominal values
    u_dc_nom: float = 540
    w_nom: float = 2*np.pi*75
    # Motor parameter estimates
    R: float = 3.6
    L_d: float = .036
    L_q: float = .051
    psi_f: float = .545
    p: int = 3
    J: float = .015


# %% Optimal references
base = BaseValues()
pars = CtrlParameters()
opt_refs = OptimalLoci(pars)
i_mtpa = opt_refs.mtpa(2*pars.i_max)
T_M_mtpa = opt_refs.torque(i_mtpa)
pars.i_d_mtpa = LUT(T_M_mtpa, i_mtpa.real)
i_mtpv = opt_refs.mtpv(2*pars.i_max)
pars.i_q_mtpv = LUT(i_mtpv.real, i_mtpv.imag)
# Plot the control loci
opt_refs.plot(2*pars.i_max, base)

# %% Choose controller
speed_ctrl = SpeedCtrl(pars)
current_ref = CurrentRef(pars)
current_ctrl = CurrentCtrl2DOFPI(pars)
datalog = Datalogger()
ctrl = VectorCtrl(pars, speed_ctrl, current_ref, current_ctrl, datalog)

# %% Profiles
# Speed reference
times = np.array([0, .5, 1, 1.5, 2, 2.5,  3, 3.5, 4])
values = np.array([0,  0, 1,   1, 0,  -1, -1,   0, 0])*base.w
mdl.speed_ref = Sequence(times, values)
# External load torque
times = np.array([0, .5, .5, 3.5, 3.5, 4])
values = np.array([0, 0, 1, 1, 0, 0])*14
mdl.mech.T_L_ext = Sequence(times, values)  # T_L_ext = Step(1, 14.6)
# Stop time of the simulation
mdl.t_stop = mdl.speed_ref.times[-1]

# %% Print the control system data
print('\nSensored vector control')
print('-----------------------')
print('Sampling period:')
print('    T_s={}'.format(pars.T_s))
print('Motor parameter estimates:')
print(('    p={}  R={}  L_d={}  L_q={}  psi_f={}'
       ).format(pars.p, pars.R, pars.L_d, pars.L_q, pars.psi_f))
print(current_ref)
print(current_ctrl)
print(speed_ctrl)

# %% Print the profiles
print('\nProfiles')
print('--------')
print('Speed reference:')
with np.printoptions(precision=1, suppress=True):
    print('    {}'.format(mdl.speed_ref))
print('External load torque:')
with np.printoptions(precision=1, suppress=True):
    print('    {}'.format(mdl.mech.T_L_ext))
