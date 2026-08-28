# Quantum Digital Signatures on QLine

This repository contains an implementation of two Quantum Digital Signature (QDS) protocols based on BB84 quantum key distribution (QKD) and the protocol described in [Grasselli et al.].

The two implementations are:

* **Block-based QDS** — uses \(n\) blocks of preshared QKD keys and produces \(2n\) signatures for each message.
* **Sequence-based QDS** — combines the QKD keys established between Alice-Bob and Alice-Charlie to produce a single signature.

Both protocols use an LFSR-based Toeplitz matrix hash and a one-time pad (OTP) for the signature construction.

The implementation supports QLine hardware simulation through `hw_sim` and `kiwi_hw_control`.

---

## Protocol overview

The protocol consists of three parties:

* **Alice** — signs the message.
* **Bob** — receives and verifies the signature first.
* **Charlie** — acts as the final verifier / trusted third party.

Alice first establishes secret QKD keys with both Bob and Charlie using BB84. These keys are then used to construct the digital signature.

The signature is based on an LFSR-generated Toeplitz matrix. For a message \(Doc\), a secret key is divided into two parts,

$$
X = s \mathbin{||} r,
$$

where \(s\) is used to construct the Toeplitz hash and \(r\) is used as an OTP.

Alice generates an irreducible polynomial \(p\), constructs the Toeplitz matrix \(T_{p,s}\), and computes

$$
Sig = (T_{p,s} \cdot Doc \mathbin{||} p) \oplus r.
$$

A verifier possessing the corresponding key can remove the OTP, reconstruct the Toeplitz matrix, and check whether the resulting hash matches the message.

The implementations use the LFSR convention described in the paper and are equivalent to the polynomial convention used in the original protocol through reciprocal polynomials. See the paper's appendix for details.

---

# Repository structure

The main protocol implementations are organised as:

```text
Q_digital_signatures/
├── block_based_QDS/
│   ├── Alice.py
│   ├── Bob.py
│   └── Charlie.py
│
├── sequence_based_QDS/
│   ├── Alice.py
│   ├── Bob.py
│   └── Charlie.py
│
├── config_test/
│   └── sim/
│       ├── alice/
│       └── bob/
│
└── ...
```

The QKD/QLine hardware-simulation components are provided by the external `hw_sim` and `kiwi_hw_control` repositories.

---

# Requirements

The protocol implementation requires:

* Python 3
* NumPy
* SciPy
* `galois`
* the QLine hardware simulator
* `kiwi_hw_control`

The exact Python package versions used for the runtime measurements in the paper were:

```text
Python 3.13.7
NumPy 2.4.6
SciPy 1.18.0
```

Additional dependencies may be required by the QKD implementation.

---

# Running the QLine hardware simulation

## 1. Build the QLine simulation components

Clone and build:

* `hw_sim`, obtaining the `simulator` executable.
* `kiwi_hw_control`, obtaining the `gc_alice` and `gc_bob` executables.

Generate the required configuration files using the configuration generator provided by `kiwi_hw_control`.

The configuration files used for the test setup are located under:

```text
applications_on_qline/Q_digital_signatures/config_test/sim/
```

---

## 2. Start the QLine hardware simulation

Run the following commands from the **`veriqloud` folder**, which should contain:

```text
hw_sim/
kiwi_hw_control/
applications_on_qline/
```

Run each command in a **separate terminal**.

### Terminal 1 — Bob's quantum simulator

```bash
hw_sim/target/release/simulator -c applications_on_qline/Q_digital_signatures/config_test/sim/bob/sim.json
```

### Terminal 2 — Alice's quantum simulator

```bash
hw_sim/target/release/simulator -c applications_on_qline/Q_digital_signatures/config_test/sim/alice/sim.json
```

### Terminal 3 — Bob's QLine control program

```bash
kiwi_hw_control/gc/target/release/gc_bob -c applications_on_qline/Q_digital_signatures/config_test/sim/bob/gc.json
```

### Terminal 4 — Alice's QLine control program

```bash
kiwi_hw_control/gc/target/release/gc_alice -c applications_on_qline/Q_digital_signatures/config_test/sim/alice/gc.json
```

These four processes provide the simulated QLine environment used by the QDS implementation.

---

# Running the QDS protocols

After starting the four QLine simulation processes above, the QDS protocol can be run.

The following commands should be executed from the **`Q_digital_signatures` folder**.

Each party should be started in a **separate terminal**.

## Block-based QDS

Run:

### Terminal 5 — Charlie

```bash
python3 -m block_based_QDS.Charlie
```

### Terminal 6 — Bob

```bash
python3 -m block_based_QDS.Bob
```

### Terminal 7 — Alice

```bash
python3 -m block_based_QDS.Alice
```

## Sequence-based QDS

Alternatively, run the sequence-based implementation:

### Terminal 5 — Charlie

```bash
python3 -m sequence_based_QDS.Charlie
```

### Terminal 6 — Bob

```bash
python3 -m sequence_based_QDS.Bob
```

### Terminal 7 — Alice

```bash
python3 -m sequence_based_QDS.Alice
```

Do **not** run both QDS protocols simultaneously using the same QLine configuration unless the configuration has been specifically prepared for this.

---

# Block-based QDS

The block-based protocol establishes \(n\) blocks of secret key between Alice and Bob and \(n\) blocks between Alice and Charlie.

Each block has length \(3b_H\):

$$
X^j = s^j \mathbin{||} r^j,
$$

where:

* \(s^j\) contains \(b_H\) bits and is used to generate the Toeplitz hash;
* \(r^j\) contains \(2b_H\) bits and is used as an OTP.

Alice generates \(2n\) signatures, one for each key block.

Bob receives Alice's document and all signatures. He can directly verify the signatures corresponding to his own key and also receives half of Charlie's key blocks through the key-exchange stage.

Bob therefore verifies

$$
\frac{3n}{2}
$$

signatures.

If Bob accepts, he forwards the signed document to Charlie. Charlie performs the corresponding verification using his own key blocks and the key blocks received from Bob.

Charlie accepts the signature if the number of detected errors is at most \(e_{max}\).

The security parameters are chosen such that

$$
\varepsilon_{\mathrm{rep}}
+
\varepsilon_{\mathrm{for}}
<10^{-10}.
$$

The required parameters are:

* \(b_M\): message length in bits
* \(n\): number of signature blocks
* \(b_H\): hash output / LFSR state length
* \(b'_H\): authentication hash length
* \(e_{max}\): maximum number of verification errors accepted by Charlie

---

# Sequence-based QDS

The sequence-based protocol uses one combined key derived from the keys established between Alice-Bob and Alice-Charlie.

Alice establishes:

$$
X_B
$$

with Bob and

$$
X_C
$$

with Charlie.

The two keys are combined to form

$$
X = X_B \oplus X_C.
$$

The resulting key is divided into

$$
X=s\mathbin{||}r.
$$

Alice generates one irreducible polynomial \(p\), constructs the corresponding Toeplitz matrix, and produces

$$
Sig=(T_{p,s}\cdot Doc\mathbin{||}p)\oplus r.
$$

Alice sends the signed document to Bob.

The order of the subsequent communication is important:

1. Alice sends \(\{Doc,Sig\}\) to Bob.
2. Bob forwards \(\{Doc,Sig\}\) and his key \(X_B\) to Charlie.
3. Charlie sends \(X_C\) to Bob.
4. Bob and Charlie reconstruct the combined key.
5. Bob verifies the signature.
6. Bob sends his verification result to Charlie.
7. Charlie verifies the signature independently.
8. Charlie accepts only if his verification succeeds and Bob has also reported successful verification.

Unlike the block-based protocol, the sequence-based protocol uses only one signature per message.

---

# BB84 QKD

Before running either QDS protocol, Alice establishes secret keys with Bob and Charlie using BB84.

In the current implementation, Alice prepares qubits in the four states

$$
\{|+\rangle,|-\rangle,|+i\rangle,|-i\rangle\},
$$

corresponding to the two possible bit values in the \(X\)- and \(Y\)-bases.

The QKD procedure consists of:

1. Alice prepares and sends the qubits.
2. Bob or Charlie randomly measures each qubit in the \(X\)- or \(Y\)-basis.
3. Alice and the receiver perform basis reconciliation.
4. A subset of the resulting key is used to estimate the QBER.
5. The protocol aborts if the QBER exceeds the tolerated value.
6. The remaining key undergoes LDPC error correction.
7. Privacy amplification is applied using a Toeplitz-matrix-based two-universal hash function.
8. Alice and the receiver obtain a shared secure key.

The procedure is performed separately between:

```text
Alice <-> Bob
Alice <-> Charlie
```

The QDS protocol then consumes these established keys.

---

# Authentication and preshared keys

The security analysis assumes authenticated classical communication.

For the block-based protocol, Bob and Charlie require an authenticated channel to exchange key blocks and their positions. In the theoretical resource analysis, this authentication uses a Wegman-Carter construction with an LFSR-based Toeplitz hash.

The total preshared-bit requirement for the block-based protocol is

$$
l_{\mathrm{total}}
=
9nb_H+n\log_2 n+5b'_H.
$$

For the sequence-based protocol,

$$
l_{\mathrm{total}}
=
6b_H+5b'_H.
$$

These quantities include the secret key material required by the QDS protocol and the authenticated Bob-Charlie communication considered in the paper.

The current implementation focuses on the QKD and QDS protocol execution; the full theoretical accounting of authentication resources is described in the paper.

---

# Parameter selection

The parameters of both protocols can be optimized numerically for a chosen message length \(b_M\).

## Block-based QDS

The optimization searches over:

```text
n
b_H
b'_H
e_max
```

and minimizes one of:

```text
l_total
l_AliceBob
l_BobCharlie
```

subject to

```text
epsilon_rep + epsilon_for < 1e-10
```

For the parameter sets reported in the paper, the optimized values of \(b_H\) increase approximately logarithmically with message length.

## Sequence-based QDS

The sequence-based protocol optimizes:

```text
b_H
b'_H
```

under the same security requirement.

The detailed optimization procedure and fitted scaling relations are given in the paper.

---

# Runtime

Runtime measurements in the paper were performed on:

```text
Apple M2
8 GB RAM
macOS Sequoia 15.6.1
Python 3.13.7
NumPy 2.4.6
SciPy 1.18.0
```

For the block-based implementation, an \(80,000\)-bit message (approximately 10 kB) required approximately:

```text
Alice signing:       21.8 s
Bob verification:    15.5 s
Charlie verification: 16.0 s
```

For an \(8,000,000\)-bit message (approximately 1 MB), the measured signing and verification times were approximately:

```text
Alice signing:       2220 s
Bob verification:    1650 s
Charlie verification: 1710 s
```

For the sequence-based implementation, the corresponding runtime is substantially lower because only one signature is generated.

The main computational bottleneck identified in the implementation is the sequential generation of LFSR states used to construct the Toeplitz matrix. Although the subsequent matrix-vector multiplication has

$$
O(b_M b_H)
$$

complexity, the practical runtime is dominated by LFSR state generation.

---

# Security

The implementations are based on information-theoretically secure primitives, assuming the security assumptions of the underlying QKD and QDS protocols.

For the block-based QDS implementation, the relevant security bounds are

$$
\varepsilon_{\mathrm{for}}
=
\Xi\left(
\frac{n}{2}-e_{max},
\frac{n}{2},
b_M2^{1-b_H}
\right),
$$

and

$$
\varepsilon_{\mathrm{rep}}
=
\max\left\{
\prod_{i=0}^{e_{max}}
\frac{n/2-i}{n-i},
\frac{b_M+4nb_H}{2^{b'_H-1}}
\right\}.
$$

For the sequence-based implementation,

$$
\varepsilon_{\mathrm{for}}
=
\frac{b_M}{2^{b_H-1}},
$$

and

$$
\varepsilon_{\mathrm{rep}}
=
\max\left\{
\frac{2b_H+b_M}{2^{b'_H-1}},
\frac{3b_H}{2^{b'_H-1}}
\right\}.
$$

The numerical optimization used in this implementation requires

$$
\varepsilon_{\mathrm{rep}}
+
\varepsilon_{\mathrm{for}}
<10^{-10}.
$$

Note that these bounds concern the QDS protocol. The security and correctness parameters of the underlying QKD implementation are treated separately in the paper.

---

# Important implementation note: LFSR convention

The implementation uses the LFSR convention

$$
P(x)
=
p_{b_H}x^{b_H}
+\cdots+
p_1x+1,
$$

with

$$
P=(p_1,\ldots,p_{b_H}).
$$

This differs in notation from the original QDS paper, which writes the polynomial coefficients in the opposite order.

The two representations correspond to reciprocal polynomials. Therefore, irreducibility is preserved and the same security bound applies.

This distinction is important when comparing the implementation against other LFSR libraries or reproducing the protocol from the original paper.

---

# Reproducing the results

The optimized parameter sets used for the runtime measurements are given in the paper.

For block-based QDS, the runtime measurements use the parameter sets optimized with \(l_{total}\) as the objective function.

For sequence-based QDS, the runtime measurements similarly use the parameter sets optimized with \(l_{total}\).

The implementation can therefore be used to reproduce the runtime measurements and investigate the scaling of:

* signing time;
* verification time;
* QKD runtime;
* LFSR generation;
* Toeplitz matrix construction;
* message length;
* optimized security parameters.

---

# References

The implementations are based primarily on:

* Grasselli et al., *[Quantum Digital Signatures protocol reference]*.
* Yin et al., *[Experimental QDS reference]*.
* Garcia et al., *[QDS protocol reference]*.
* Bennett and Brassard, BB84 quantum key distribution.
* Krawczyk, LFSR-based universal hashing.
* Aagren et al., LFSR-based hashing.
* Cai et al., LFSR-based universal hashing.

See the accompanying paper and bibliography for the complete references.

---

# License

This project is licensed under the GPL-3.0 License.

Third-party dependencies are distributed under their respective licenses. Users should comply with the license terms of all dependencies when redistributing or modifying this project.

---

# Code access

The source code for the QDS implementations is contained in this repository.

For further details on the protocol construction, security analysis, parameter optimization, QKD implementation, required qubit numbers, and LFSR/Toeplitz implementation, see the accompanying paper:

**“Practical Implementation of Quantum Digital Signatures on BB84-based Hardware”**

by See Min Lim.

---

# Acknowledgements

This work was carried out at VeriQloud in collaboration with École Polytechnique and the National University of Singapore.

The implementation makes use of the QLine hardware/software stack and associated simulation tools.
