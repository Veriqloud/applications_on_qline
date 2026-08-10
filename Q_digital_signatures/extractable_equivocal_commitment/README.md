# Subprotocol - extractable equivocal commitment

  

A two parties protocol which enables the server to commit a set of values. Then the clinet is able to chose any subset of values to reveal.

  

## protocol parameteres


- Security parameter (λ): Determines the bit length of the randomness used in commitments.

- Number of commitments (n): The sender commits to n values.

- Hash function : A hash function that takes inputs of size (λ + 1) bits and outputs (λ + 1) bits. We use sha256 for example.



## protocol Steps

----


### commitment phase (Server)

  

- input

	- Security parameter λ.
	- Commitment content array bi: n values {bi} where i ∈ [n].

  

- steps

	For each i:
	
		Sample a random ri of length λ bits.
		Compute the commitment comi = Hash(bi || ri).

	Store the state st = {bi, ri}i∈[n] (i.e., the original values and randomness).

	  

	Send the state st and the commitments {comi}i∈[n] to the client.

	So each comi serves as a commitment to bi using a hidden random ri.

  

----

  

### reveal phase (Client)

  

- input

	- The stored state st = {bi, ri}i∈[n]
	- A subset of indices T ⊆ [n], the set to reveal.

  

- steps

	Extract {bi, ri}i∈T from st.
	So the sender reveals selected commitments by providing both bi and ri.

  
  

----

  

### verification phase (Client)

  

- input

	- The commitments {comi}i∈[n]
	- A subset of indices T
	- The revealed values {bi, ri}i∈T

  

- steps

  
	
	Check that H(bi || ri) = comi for all i ∈ T.

	If any check fails, output ⊥ (invalid).

	Otherwise, output {bi}i∈T (the revealed values).

	  

	Ensures the sender cannot cheat by changing bi or ri after committing.

  

----
