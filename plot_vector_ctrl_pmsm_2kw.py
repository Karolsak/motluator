"""
Vector-Controlled 2.2-kW PMSM Drive
===================================

This example simulates sensorless vector control of a 2.2-kW PMSM drive.

"""

# %%
# Import the packages.
import numpy as np
import motulator as mt

# %%
# Compute base values based on the nominal values (just for figures).

base = mt.BaseValues(
    U_nom=370, I_nom=4.3, f_nom=75, tau_nom=14, P_nom=2.2e3, p=3)

# %%
# Configure the system model.

motor = mt.SynchronousMotor()
mech = mt.Mechanics()
conv = mt.Inverter()
mdl = mt.SynchronousMotorDrive(motor, mech, conv)

# %%
# Configure the control system.

pars = mt.SynchronousMotorVectorCtrlPars(sensorless=True,use_injection=True)
ctrl = mt.SynchronousMotorVectorCtrl(pars)

# %%
# Set the speed reference and the external load torque.

# Speed reference
times = np.array([0, .225, .35, .475, .535, .585, .7, .8, 1])*4
values = np.array([0, 0, .1, .1, 0, -.1, -.1, 0, 0])*base.w
ctrl.w_m_ref = mt.Sequence(times, values)
# External load torque
times = np.array([0, .02, .02, .85, .85, 1])*4
values = np.array([0, 0, .9, .9, 0, 0])*base.tau_nom
mdl.mech.tau_L_ext = mt.Sequence(times, values)

# %%
# Create the simulation object and simulate it.

sim = mt.Simulation(mdl, ctrl, pwm=False)
sim.simulate(t_stop=4)

# %%
# Plot results in per-unit values.

mt.plot(sim, base=base)
