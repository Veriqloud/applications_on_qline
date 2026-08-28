import math
import numpy as np
from scipy.stats import binom
import argparse


def repudiation_prob_P1(bM, bH, bH_prime):
    left_term = (2 * bH + bM)/math.pow(2, bH_prime - 1)
    right_term = (3 * bH)/math.pow(2, bH_prime - 1)

    return max(left_term, right_term)

def forgery_prob_P1(bM, bH):
    return bM/(math.pow(2, bH - 1))

def find_optimal_params(func, bM, total_budget=1e-10,      # even n, per protocol structure
                          bH_range=None):             # emax <= n/2

    best = None  # (lP, n, bH, emax, b_prime_H)
    if bH_range is None:
        bH_range=range(int(np.log2(bM) + 1), 128)

    for bH in bH_range:
        # quick necessary check before looping emax: p = bM * 2^(1-bH) <= 1
        p = bM * 2**(1 - bH)
        if p > 1:
            continue  # bH too small at this bM, skip entirely

        eps_for = forgery_prob_P1(bM, bH) 
        remaining = total_budget - eps_for
        if remaining <= 0:
            continue

        #comb_term = compute_combinatorial_term(n, emax)
        #if comb_term > remaining:
        #    continue
        numerator = max(2 * bH + bM, 3 * bH)

        # solve b'_H analytically, then round UP (ceil) since b'_H must be an integer
        # and rounding down could violate the security bound
        raw_b_prime_H = math.log2(numerator/ remaining) + 1
        b_prime_H = math.ceil(raw_b_prime_H)

        # verify the rounded integer value actually satisfies the bound
        eps_rep = numerator / (2**(b_prime_H - 1))
        #eps_rep = max(comb_term, eps_prime)
        total = eps_for + eps_rep

        if total > total_budget:
            continue  # shouldn't happen given ceil, but guard anyway

        l = func(bH, b_prime_H)

        if best is None or l < best[0]:
            best = (l,  bH, b_prime_H, total, eps_for, eps_rep)

    return best


def l_total(bH, b_prime_H):
    return 6 * bH + 5 * b_prime_H

def l_AliceBob(bH, b_prime_H):
    return 3*bH 

def l_BobCharlie(bH, b_prime_H):
    return 5*b_prime_H

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find Optimal Parameters for sequence-based QDS")
    parser.add_argument("-f", "--func",
                        type=str,
                        default="l_total",
                        choices=["l_total", "l_AliceBob", "l_BobCharlie"],
                        help="Objective function to optimize over"
                    )
    parser.add_argument("-bM", "--bM", type=int,
                        help="bit length of message. Recommended range: 80 to 80,000,000")

    args = parser.parse_args()
    f = {"l_total": l_total, "l_AliceBob": l_AliceBob, "l_BobCharlie": l_BobCharlie}[args.func]  

    l,  bH, b_prime_H, total, eps_for, eps_rep = find_optimal_params(f, args.bM)
    print(f"bH: {bH}, b_prime_H: {b_prime_H}")