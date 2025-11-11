from decimal import Decimal

def round_step(num: float, step: float) -> float:
    """
    Rounds a float to a given step size
    """
    if step == 0 or step is None:
        return num  # No rounding if step is 0 or None
    
    try:
        num = Decimal(str(num))
        step_decimal = Decimal(str(step))
        return float(num - num % step_decimal)
    except Exception:
        return num  # Return original number if conversion fails


### FIX FOR STEP > 1 ###

# import numpy as np
# from numba import njit, float64

# @njit(float64(float64, float64), cache=True)
# def round_step(num: float, step: float) -> float:
#     """
#     Rounds a float to a given step size
#     """
#     p = int(1/step)
#     return np.floor(num*p)/p