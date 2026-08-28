import math
import numpy as np
from scipy.stats import binom
import argparse


def repudiation_prob(n, bM, bH, bH_prime, e_max):
    right_term = (bM + 4 * n * bH)/math.pow(2, bH_prime - 1)
    left_term = 1
    for i in range(e_max):
        left_term *= (n/2 - i)/(n-i)

    return max(left_term, right_term)


def forgery_prob(n, bM, bH, e_max):
    a = n//2 - e_max
    b = n//2
    c = bM * math.pow(2, 1 - bH)
    #print(a, b, c)

    Xi = binom.sf(a - 1, b, c)
    return Xi


def compute_combinatorial_term(n, e_max):
    left_term = 1
    for i in range(e_max):
        left_term *= (n//2 - i)/(n-i)
    return left_term


def find_optimal_params(func, bM, total_budget=1e-10,
                          n_range=range(2, 500, 2),      # even n, per protocol structure
                          bH_range=None):             # emax <= n/2

    best = None  # (lP, n, bH, emax, b_prime_H)
    if bH_range is None:
        bH_range=range(int(np.log2(bM) + 1), 128)

    for n in n_range:
        for bH in bH_range:
            # quick necessary check before looping emax: p = bM * 2^(1-bH) <= 1
            p = bM * 2**(1 - bH)
            if p > 1:
                continue  # bH too small at this bM, skip entirely

            for emax in range(0, n // 2 + 1):
                eps_for = forgery_prob(n, bM, bH, emax) 
                remaining = total_budget - eps_for
                if remaining <= 0:
                    continue

                comb_term = compute_combinatorial_term(n, emax)
                if comb_term > remaining:
                    continue

                # solve b'_H analytically, then round UP (ceil) since b'_H must be an integer
                # and rounding down could violate the security bound
                raw_b_prime_H = math.log2((bM + 4*n*bH) / remaining) + 1
                b_prime_H = math.ceil(raw_b_prime_H)

                # verify the rounded integer value actually satisfies the bound
                eps_prime = (bM + 4*n*bH) / (2**(b_prime_H - 1))
                eps_rep = max(comb_term, eps_prime)
                total = eps_for + eps_rep

                if total > total_budget:
                    continue  # shouldn't happen given ceil, but guard anyway

                l = func(n, bH, b_prime_H)

                if best is None or l < best[0]:
                    best = (l, n, bH, emax, b_prime_H, total)

    return best


def l_total(n, bH, b_prime_H):
    return 9*n*bH + n*math.log2(n) + 5*b_prime_H

def l_AliceBob(n, bH, b_prime_H):
    return 3*n*bH 

def l_BobCharlie(n, bH, b_prime_H):
    return 3*n*bH + n*math.log2(n) + 5*b_prime_H

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find Optimal Parameters for block-based QDS")
    parser.add_argument("-f", "--func",
                        type=str,
                        default="l_total",
                        choices=["l_total", "l_AliceBob", "l_BobCharlie"],
                        help="Objective function to optimize over"
                    )
    parser.add_argument("-bM", "--bM", type=int,
                        help="bit length of message. Recommended range: 80 to 8,000,000")

    args = parser.parse_args()
    f = {"l_total": l_total, "l_AliceBob": l_AliceBob, "l_BobCharlie": l_BobCharlie}[args.func]  

    l, n, bH, emax, b_prime_H, total = find_optimal_params(f, args.bM)
    print(f"n: {n}, bH: {bH}, emax: {emax}, b_prime_H: {b_prime_H}")