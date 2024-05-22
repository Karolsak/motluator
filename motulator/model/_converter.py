"""
Power converter models.

An inverter with constant DC-bus voltage and a frequency converter with a diode
front-end rectifier are modeled. Complex space vectors are used also for duty
ratios and switching states, wherever applicable. In this module, all space
vectors are in stationary coordinates. 

"""
import numpy as np


# %%
class Inverter:
    """
    Inverter with constant DC-bus voltage and switching-cycle averaging.

    Parameters
    ----------
    u_dc : float
        DC-bus voltage (V).

    """

    def __init__(self, u_dc):
        self.u_dc0 = u_dc

    @staticmethod
    def ac_voltage(q, u_dc):
        """
        Compute the AC-side voltage of a lossless inverter.

        Parameters
        ----------
        q : complex
            Switching state vector.
        u_dc : float
            DC-bus voltage (V).

        Returns
        -------
        u_c : complex
            AC-side converter voltage (V).

        """
        u_c = q*u_dc
        return u_c

    @staticmethod
    def dc_current(q, i_c):
        """
        Compute the DC-side current of a lossless inverter.

        Parameters
        ----------
        q : complex
            Switching state vector.
        i_c : complex
            AC-side converter current (A).

        Returns
        -------
        i_dc : float
            DC-side current (A).

        """
        i_dc = 1.5*np.real(q*np.conj(i_c))
        return i_dc

    def meas_dc_voltage(self):
        """
        Measure the DC-bus voltage.

        Returns
        -------
        float
            DC-bus voltage (V).

        """
        return self.u_dc0


# %%
class FrequencyConverter(Inverter):
    """
    Frequency converter.

    This extends the Inverter class with models for a strong grid, a
    three-phase diode-bridge rectifier, an LC filter, and a three-phase
    inverter.

    Parameters
    ----------
    L : float
        DC-bus inductance (H).
    C : float
        DC-bus capacitance (F).
    U_g : float
        Grid voltage (V, line-line, rms).
    f_g : float
        Grid frequency (Hz).

    """

    def __init__(self, L, C, U_g, f_g):
        # pylint: disable=super-init-not-called
        self.L, self.C = L, C
        # Initial value of the DC-bus inductor current
        self.i_L0 = 0
        # Initial value of the DC-bus voltage
        self.u_dc0 = np.sqrt(2)*U_g
        # Peak-valued line-neutral grid voltage
        self.u_g = np.sqrt(2/3)*U_g
        # Grid angular frequency
        self.w_g = 2*np.pi*f_g

    def grid_voltages(self, t):
        """
        Compute three-phase grid voltages.

        Parameters
        ----------
        t : float
            Time (s).

        Returns
        -------
        u_g_abc : ndarray of floats, shape (3,)
            Phase voltages (V).

        """
        theta_g = self.w_g*t
        u_g_abc = self.u_g*np.array([
            np.cos(theta_g),
            np.cos(theta_g - 2*np.pi/3),
            np.cos(theta_g - 4*np.pi/3)
        ])
        return u_g_abc

    def f(self, t, u_dc, i_L, i_dc):
        """
        Compute the state derivatives.

        Parameters
        ----------
        t : float
            Time (s).
        u_dc : float
            DC-bus voltage (V) over the capacitor.
        i_L : float
            DC-bus inductor current (A).
        i_dc : float
            Current to the inverter (A).

        Returns
        -------
        list, length 2
            Time derivative of the state vector, [d_u_dc, d_i_L]

        """
        # Grid phase voltages
        u_g_abc = self.grid_voltages(t)
        # Output voltage of the diode bridge
        u_di = np.amax(u_g_abc, axis=0) - np.amin(u_g_abc, axis=0)
        # State derivatives
        d_u_dc = (i_L - i_dc)/self.C
        d_i_L = (u_di - u_dc)/self.L
        # The inductor current cannot be negative due to the diode bridge
        if i_L < 0 and d_i_L < 0:
            d_i_L = 0
        return [d_u_dc, d_i_L]
