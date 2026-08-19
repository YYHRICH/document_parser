## HIGHER GENUS GROMOV-WITTEN THEORY OF ONE-PARAMETER CALABI-YAU THREEFOLDS II: FEYNMAN RULE AND ANOMALY EQUATIONS

## PATRICK LEI

Abstract. We prove the Feynman rule conjectured by Bershadsky-CecottiOoguri-Vafa [BCOV94] and the anomaly equations conjectured by YamaguchiYau [YY04] for the Gromov-Witten theory of the Calabi-Yau threefolds Z 6 ⊂ P (1 , 1 , 1 , 1 , 2), Z 8 ⊂ P (1 , 1 , 1 , 1 , 4), and Z 10 ⊂ P (1 , 1 , 1 , 2 , 5). These determine the generating series F g of genus g Gromov-Witten invariants recursively from the lower-genus F h&lt;g up to 3 g -3 unknown parameters.

## Contents

| 1.                   | Introduction                                     |   2 |
|----------------------|--------------------------------------------------|-----|
| 1.1.                 | Historical overview                              |   2 |
| 1.2.                 | Setup and past work                              |   3 |
| 1.3.                 | Feynman rule                                     |   4 |
| 1.4.                 | Anomaly equations                                |   7 |
| 1.5.                 | Outline                                          |   7 |
| 1.6.                 | Conventions                                      |   7 |
| Acknowledgements     | Acknowledgements                                 |   8 |
| 2.                   | MSP [0] and [1] theories                         |   8 |
| 2.1.                 | The MSP [0 , 1] theory                           |   8 |
| 2.2.                 | The MSP [0] and [1] theories                     |  10 |
| 2.3.                 | Polynomiality of the [1] theory                  |  12 |
| 2.4.                 | Vanishing of the [0] theory                      |  14 |
| 3.                   | The A -model Feynman rule                        |  17 |
| 3.1.                 | Factorization of the [0] theory                  |  18 |
| 3.2.                 | Polynomiality of the [0] theory and the A theory |  19 |
| 3.3.                 | Choice of gauge                                  |  24 |
| 4.                   | The B-model Feynman rule                         |  25 |
| 4.1.                 | B-model geometric quantization                   |  26 |
| 4.2.                 | Factorization of the quantization action         |  27 |
| 4.3.                 | Modification of the A-model quantization         |  28 |
| 4.4.                 | Equality of A-model and B-model potentials       |  30 |
| 5. Anomaly equations | 5. Anomaly equations                             |  32 |
| References           | References                                       |  34 |

## 1. Introduction

1.1. Historical overview. Despite its origin in theoretical physics as a duality between A-model and B-model topological string theories, mirror symmetry has sparked significant interest in mathematics, starting with the landmark paper [COGP92], which gave predictions for the number of genus zero curves of any degree on the quintic threefold. Even though their predictions differ from the actual numbers of curves, they sparked a significant change in the field of enumerative geometry - namely, to consider deformation-invariant virtual counts of curves. The first mathematical theory constructed to satisfy this property is Gromov-Witten theory (a formalization of A-model invariants), which was developed in symplectic topology by various authors [RT95; LT98b; Sie98; FO99; Rua99] and in algebraic geometry by Behrend-Fantechi and Li-Tian [BF97; Beh97; LT98a].

For physical reasons, a central problem in Gromov-Witten theory is to compute the Gromov-Witten invariants of compact Calabi-Yau threefolds. For simplicity, we will restrict to the case when h 2 = 1 and in particlar to those which arise as complete intersections in weighted projective spaces, of which there are 13 examples (see [HKQ09, § 4] for a complete list). We will list (very incompletely) some historical developments in mathematics and physics:

- A theorem determining the genus zero invariants generalizing the predictions of [COGP92] was proved by Givental and Lian-Liu-Yau [Giv96; LLY97] for complete intersections in projective space and by Coates-Corti-LeeTseng and Wang [CCLT09; Wan20] for complete intersections in weighted projective spaces.
- Bershadsky-Cecotti-Ooguri-Vafa [BCOV94] studied the B-model KodairaSpencer gravity and predicted that the generating series F g of genus g Gromov-Witten invariants can be computed recursively using F h&lt;g by a Feynman rule up to a finite ambiguity. Mathematically, this corresponds to a sum over stable graphs, which index combinatorial strata of the moduli space M g,n of stable curves.
- Yamaguchi-Yau [YY04] studied the B-model theory further and predicted that a normalized generating series P g of genus g Gromov-Witten invariants is a polynomial in five explicit generators for Z 5 ⊂ P 4 , Z 6 ⊂ P (1 4 , 2), Z 8 ⊂ P (1 4 , 4), and Z 10 ⊂ P (1 3 , 2 , 5). They also predicted that these polynomials satisfy differential equations in the generators, which we will refer to as Anomaly Equations . 1 These predictions were extended to the other examples by Huang-Klemm-Quackenbush [HKQ09].
- In mathematics, exact formulae for the genus 1 invariants were proved for complete intersections in projective spaces by Zinger and Popa [Zin09; Pop13] and for hypersurfaces in weighted projective spaces by the author [Lei24a].
- An exact formula for the genus 2 invariants of the quintic was proved by Guo-Janda-Ruan [GJR17] pending the proof of foundational results in logarithmic geometry. This was followed by a proof [GJR18] of the Anomaly Equations and finite generation conjecture, as well as some other results, for the quintic threefold.

1 These are typically referred to as Holomorphic Anomaly Equations in the mathematics literature, which is technically inaccurate. In physics, the B-model partition function F B g ( t, ¯ t ) has an antiholomorphic part, which is governed by the physical Holomorphic Anomaly Equations.

- The Feynman rule, Anomaly Equations, and finite generation conjecture were proved independently by Chang-Guo-Li [CGL21; CGL19] using the theory of Mixed-Spin-P (MSP) fields developed in [CLLL19; CLLL22; CL20; CGLL21]. 2 Using a slight generalization of their approach, the author proved the finite generation conjecture [Lei24a] for hypersurfaces in weighted projective space.
- 1.2. Setup and past work. Let a = (1 , 1 , 1 , 1 , 2), (1 , 1 , 1 , 1 , 4), or (1 , 1 , 1 , 2 , 5), k := ∑ 5 i =1 a i , and set p k := k a 1 ··· a 5 . The I -function of Z = Z k ⊂ P ( a ) is given by

[[FORMULA_UNAVAILABLE]]

where H = c 1 ( O P ( a ) (1)). If we set r := k k a a 1 1 ··· a a 5 5 , then I ( q, z ) has radius of convergence 1 r .

Remark 1.1 . In [Giv96] and other work, the I -function differs from ours by a prefactor of q H z . In particular, applying zq d d q to the usual conventions corresponds to applying H + zq d d z to our I -function.

Our choice is natural from the perspective of quasimap theory. There, our I -function is obtained by localization on the stacky loop space [CCK15, Proposition 4.9] and appears in the wall-crossing formula of [Zho22].

Define D := q d d q and define

[[FORMULA_UNAVAILABLE]]

Yamaguchi-Yau [YY04] defined infinitely many generators

[[FORMULA_UNAVAILABLE]]

For simplicity, denote A := A 1 and B := B 1 .

Remark 1.2 . Our generators differ from the generators in [YY04; HKQ09] slightly. The variables differ by ψ HKQ = ( rq ) -1 , and the generators in [HKQ09] are defined by

[[FORMULA_UNAVAILABLE]]

In particular, we have the relations

[[FORMULA_UNAVAILABLE]]

2 A parameter N , which is a positive integer, was introduced in [CGLL21] and the resulting theory was originally referred to as N -Mixed-Spin-P (NMSP) fields. In this paper, we will simply refer to the theory with arbitrary N as MSP fields.

Lemma 1.3 ([YY04]) . The ring R := Q [ A,B,B 2 , B 3 , Y ] contains all A m and B m for m ≥ 0 . In particular, we have the relations

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

where r 0 and r 1 are given in Table 1.

Table 1. Values of r 0 , r 1 , a 0 ,k , and a 1 ,k for different k

|   k | r 0   | r 1       | a 0 ,k   | a 1 ,k   |
|-----|-------|-----------|----------|----------|
|   6 | 13 36 | 5 162     | 1 2      | - 7 4    |
|   8 | 11 32 | 105 4096  | 1 3      | - 11 6   |
|  10 | 3 10  | 189 10000 | 1 6      | - 17 12  |

We now define the generating function

[[FORMULA_UNAVAILABLE]]

where the values of a 0 ,k = 1 6 ∫ Z H 3 and a 1 ,k = -1 24 ∫ Z c 2 ( Z ) ∪ H are given in Table 1. This is not quite so well-behaved, so we will normalize it by defining

[[FORMULA_UNAVAILABLE]]

for any ( g, m ) satisfying 2 g -2 + m&gt; 0. These satisfy the recursive relation

[[FORMULA_UNAVAILABLE]]

and therefore can be computed from P 0 , 3 = 1, P 1 , 1 , and P g ≥ 2 . The main result of our previous work [Lei24a] is the following:

Theorem 1.4. For any ( g, m ) satisfying 2 g -2 + m&gt; 0 , P g,m ∈ R .

We also proved the following exact formula for the genus 1 invariants of Z :

## Theorem 1.5. We have

[[FORMULA_UNAVAILABLE]]

For clarity, note that χ ( Z 6 ) = -204 , χ ( Z 8 ) = -296 , and χ ( Z 10 ) = -288 .

## 1.3. Feynman rule.

Definition 1.6. Define the physicists' propogators by the formulae

[[FORMULA_UNAVAILABLE]]

For a choice of 'gauge' G := ( c 11 , c 12 , c 2 , c 3 ), where c 11 , c 12 ∈ Q [ X ] 1 , c 2 ∈ Q [ X ] 2 , and c 3 ∈ Q [ X ] 3 , define

[[FORMULA_UNAVAILABLE]]

Define I 22 := 1 + D ( D ( I 2 I 0 ) + I 0 I 0 I 11 ) and I 33 := I 11 . Let φ i = I 0 · · · I ii H i for i = 0 , 1 , 2 , 3 and let ψ denote the ancestor class on M g,n .

Definition 1.7. Define the B-model Gromov-Witten correlators P g,m,n by

[[FORMULA_UNAVAILABLE]]

Here, (2 g + m + n -3) n is the falling Pochhammer symbol.

Note that these agree with the GW invariants

[[FORMULA_UNAVAILABLE]]

whenever ( g, m ) = (1 , 0), in which case the GW invariants is ( n -1)! χ ( Z ) 24 . Later, we will discover the meaning of this term.

̸

Definition 1.8. Let G g,ℓ be the set of all stable graphs of genus g and ℓ legs and define

[[FORMULA_UNAVAILABLE]]

where the contribution of a stable graph is defined by the following construction:

- At each leg, we place φ 1 -E G ψ φ 0 ψ or φ 0 ψ ;
- At each edge, we place the bivector

[[FORMULA_UNAVAILABLE]]

- At each vertex, we place the linear map

[[FORMULA_UNAVAILABLE]]

The main result of this paper is the following polynomiality result for f B g,m,n .

Theorem 1.9 (Corollary 4.9) . For any g, m, n and any choice of gauge G , we have

[[FORMULA_UNAVAILABLE]]

If we specialize to m = n = 0, then G g, 0 contains a leading graph Γ 0 with exactly one vertex (of genus g ) and no edges. This graph contributes P g , while other graphs contribute linear combinations of products of P h&lt;g,m,n and the propogators. Therefore, if we know all P h&lt;g,m,n , the formula

̸

[[FORMULA_UNAVAILABLE]]

implies that to compute P g , it suffices to compute f B g ∈ Q [ X ] 3 g -3 . Because the degree 0 invariant

[[FORMULA_UNAVAILABLE]]

was already computed by Faber-Pandharipande [FP00], this allows us to fix the constant term of f B g as p g -1 k N g, 0 .

We will prove this result by reconstructing it from the A-model. We begin by constructing an A-model R -matrix, which will act on the Gromov-Witten potential of Z . It is engineered such that its edge contributions match the B-model edge contributions as much as possible.

Definition 1.10. In the basis φ 0 , . . . , φ 3 of H Z , define the A -model R -matrix by

[[FORMULA_UNAVAILABLE]]

where we define E G 1 φψ := -E G ψ E G φφ -E G φψ and E G 1 ψ 2 := -E G ψ E G φψ -E G ψψ .

We will now define an A-model Feynman rule.

Definition 1.11. For a ∈ { 0 , 1 , 2 , 3 } n and b ∈ Z n ≥ 0 , define

[[FORMULA_UNAVAILABLE]]

where the contribution of a stable graph is defined by the following construction:

- At each leg, we place R A , G ( z ) -1 φ a ψ b ;
- At each edge, we place the bivector

[[FORMULA_UNAVAILABLE]]

- At each vertex, we place the linear map

[[FORMULA_UNAVAILABLE]]

Using the theory of MSP fields, we will prove a polynomiality result for f A , G g, a , b . Along the way, we discover that the MSP R -matrix defined in [Lei24a] (see (2.1)) factors as the product of a matrix R X which satisfies an X -polynomiality property and R A , G and obtain a similar degree bound for the level 0 part of the full MSP theory.

Theorem 1.12 (Corollary 3.12) . For any choice of gauge G and any g, n such that 2 g -2 + n &gt; 0 , we have

[[FORMULA_UNAVAILABLE]]

In particular, when we set a = (1 m , 0 n ) and b = (0 m , 1 n ), we define

[[FORMULA_UNAVAILABLE]]

Note that the A-model Feynman rule has three extra edge contributions, which contain four extra variables compared to the B-model Feynman rule. Remarkably, the contributions of the correction term in g = 1, the extra A-model edge contributions, and the four extra A-model variables cancel out to yield the following result.

Theorem 1.13 (Theorem 4.8) . The A-model and B-model graph sums satisfy the relation

[[FORMULA_UNAVAILABLE]]

1.4. Anomaly equations. In Section 5, we prove the following anomaly equations:

Theorem 1.14 (Theorem 5.1) . The P g,m satisfy the differential equations

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

The first equation is proved directly by differentiating the B-model Feynman rule, while the second is equivalent to a mysterious reduction of generators (Theorem 5.6) found by Yamaguchi-Yau [YY04]. In particular, they consider particular v 1 , v 2 , v 3 ∈ R and conjecture that for all g ≥ 2, P g ∈ Q [ v 1 , v 2 , v 3 , X ].

## 1.5. Outline. The paper is organized as follows:

- In § 2, we review the construction of the MSP [0 , 1] theory, construct the MSP [0] and [1] theories, and prove polynomiality of the MSP [1] theory.
- In § 3, we prove the polynomiality of the MSP [0] theory and the A-model graph sum using a bootstrapping argument when G = (0 , 0 , 0 , 0). The A-model Feynman rule for a general gauge (Theorem 1.12) follows as a corollary.
- In § 4, we rewrite both the A-model Feynman rule and B-model Feynman rule using the formalism of geometric quantization of symplectic linear transformations. We then study the effect of the extra contributions in the A-model and prove Theorem 1.13 by direct computation. The B-model Feynman rule (Theorem 1.9) follows as a corollary.
- In § 5, we prove Theorem 1.14.
- 1.6. Conventions. We will use the following conventions in this paper:
- We will ignore the odd cohomology of our target Z . All operators in this paper will preserve the Z / 2 grading on cohomology and are the identity on odd classes.
- The theory of MSP fields depends on a positive integer N . We will assume that N is an odd prime. Whenever we fix g, n , we will always assume that N ≫ 3 g -3 + n .
- We will consider T = ( C × ) N -equivariant invariants. Our convention is that after equivariant integration, we will specialize our equivariant parameters by t α = -ζ α N t . At various points in the paper, we will specialize t N = -1.
- Whenever we compute using equivariant integration, we will make the substitution q ′ = -q t N . Note the specialization t N = -1 makes q ′ = q .

Acknowledgements. The author is grateful to Chiu-Chu Melissa Liu for all of her helpful advice and for proposing this project. The author would like to thank Konstantin Aleshkin and Shuai Guo for helpful discussions, and Dimitri Zvonkine for his lectures about CohFTs and R -matrix actions at the Simons Center for Geometry and Physics in August 2023. The author would also like to thank Shuai Guo for his hospitality during the author's visit to Peking University in July 2024, when part of this work was completed. Finally, the author would like to thank Felix Janda and Yongbin Ruan for expressing interest in the results of this paper and its prequel [Lei24a].

## 2. MSP [0] and [1] theories

̸

In this section, we will define the MSP [0] theory and [1] theory and prove a polynomiality property for the [1] theory. We will refer the reader to [PPZ15] and [CGL19, § 2, Appendix C] for a discussion of CohFTs and R -matrix actions, including in the cases when R 0 = I and when source and target of the R -matrix are different vector spaces or have different pairings.

2.1. The MSP [0 , 1] theory. Let N be a positive integer. First, the stack W g,n, ( d, 0) was constructed in [Lei24b] and MSP invariants were constructed in [Lei24a] for the state space

[[FORMULA_UNAVAILABLE]]

The pairing is given by

[[FORMULA_UNAVAILABLE]]

We will now give several bases which we will consider in the rest of the paper.

- (1) We consider Z ⊔ ⊔ N α =1 pt α = ( x k/a 1 1 + · · · + x k/a 5 5 = 0) T ⊂ P ( a , 1 N ) and let p = c 1 ( O P ( a , 1 N ) (1)). Then define ϕ j := p j for j = 1 , . . . N +3;
- (2) Note that there is the natural basis { 1 , H, H 2 , H 3 } of H Z and { 1 α } N α =1 of H 1 := ⊕ α H α ;
- (3) We may normalize the previous basis 3 and consider φ b = I 0 I 11 · · · I bb H b ,
4. where I 22 = 1 + D ( D ( I 2 I 0 ) + I 1 I 0 I 11 ) and I 33 = I 11 . We will also consider ¯ 1 α = L -N +3 2 1 α .

Before we continue, we will define several CohFTs related to C using the MSP virtual localization formula [Lei24b, § 6]. First, for any smooth projective variety Z , the Gromov-Witten CohFT associated to Z is given by

[[FORMULA_UNAVAILABLE]]

3 This is related to the transformation from flat coordinates to canonical coordinates, see [Lei24a, § 5]

where st Z : M g,n ( Z, d ) → M g,n is the stabilization morphism and τ i ∈ H ∗ ( Z ). In the MSP virtual localization formula, the contribution of a vertex at level 0 is given by

[[FORMULA_UNAVAILABLE]]

Replacing [ M g,n ( Z, d )] vir by [ M g,n ( Z, d )] tw in the formula for Ω Z , we obtain the CohFT Ω Z, tw .

We will need to consider a shift of the Gromov-Witten CohFT of Z by the mirror map τ Z ( q ) := I 1 ( q ) I 0 ( q ) H . This is given by the formula

[[FORMULA_UNAVAILABLE]]

where Q ( q ) := qe I 1 ( q ) I 0 ( q ) is the mirror map.

For each of the isolated points pt α , we may consider the vertex contribution

̸

[[FORMULA_UNAVAILABLE]]

̸

These classes define a CohFT Ω pt α , tw , and restricting to the topological part

[[FORMULA_UNAVAILABLE]]

gives the topological part ω pt α , tw of the CohFT.

In [Lei24a, § 2.1], we defined MSP invariants ⟨-⟩ M g,n using virtual localization, whose explicit formula was proved in [Lei24b, § 5]. Recall that for any cohomological field theory, Givental's theory [Giv04] considers the fundamental solution of the quantum differential equation (or Dubrovin connection), which is given by

[[FORMULA_UNAVAILABLE]]

Here, { e a } is a basis of H and { e a } is its dual basis. We will now restrict to the case τ = 0 and abbreviate the fundamental solution to S M ( z ). We also considered the corresponding fundamental solutions S Z := S Z τ Z ( q ) where τ Z = I 1 ( q ) I 0 ( q ) H and S pt α := S pt α τ α , where τ α = -t α ∫ q 0 ( L ( x ) -1) d x x , where L = (1 + rx ) 1 N .

Finally, we defined the MSP R -matrix by the formula

[[FORMULA_UNAVAILABLE]]

where ∆ pt α ( z ) is the Quantum Riemann-Roch [CG07] operator given by the formula

̸

[[FORMULA_UNAVAILABLE]]

Here, the B 2 k are the Bernoulli numbers.

In [Lei24a, § 5], we explained how to use the explicit formula for the quantum differential equation given in [Lei24a, Lemma 2.18] to compute the entries of R ( z ) ∗ when the input basis is { 1 , p, . . . , p N +3 } and the output basis is { φ 0 , . . . , φ 3 } ∪ { ¯ 1 α } N α =1 . In particular, the entries are elements of R up to some normalization.

Definition 2.1 ([Lei24a, Theorem 3.6]) . Define the local theory by the formula

[[FORMULA_UNAVAILABLE]]

and the MSP [0 , 1] theory by the formula

[[FORMULA_UNAVAILABLE]]

Remark 2.2 . Note that the [0 , 1] theory was originally defined using virtual localization. The fixed loci of W g,n, ( d, 0) are described using localization graphs Θ whose vertices can be partitioned as V = V 0 ⊔ V 1 ⊔ V ∞ . We then only consider those Θ for which V ∞ = ∅ when defining the [0 , 1] theory. In [Lei24a, § 3], we proved that it is equivalent to the definition we give here. In addition, when N is very large relative to g, n , we obtain a simpler formula for the tail contributions at level 0.

Remark 2.3 . In contrast to the usual setting (see [PPZ15] for example), our R ( z ) = R 0 + R 1 z + · · · does not satisfy R 0 = Id. However, we can relate this more general case of R -matrix actions to the usual setting via the dilaton flow, for example see [CGL19, Appendix C].

2.2. The MSP [0] and [1] theories. We will now define restricted versions of the MSP [0 , 1] CohFTs, which we will call the [0] and [1] theories. First, recall that [CGL19, § 2] gives a definition of the R -matrix action on CohFTs when the source and target of R are not the same vector space. In particular, we only need that R ( -z ) ∗ R ( z ) = Id, which in particular implies that R 0 is injective.

Definition 2.4. Define the restricted R -matrices R [0] ( z ) and R [1] ( z ) by the formulae

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

Because the MSP R -matrix R ( z ) satisfies R ( -z ) ∗ R ( z ) = Id, R [0] ( z ) and R [1] ( z ) satisfy the identities

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

Definition 2.5. Define the MSP [0] theory by the formula

[[FORMULA_UNAVAILABLE]]

and the MSP [1] theory by the formula

[[FORMULA_UNAVAILABLE]]

Our immediate goal is now to prove a polynomiality result for the MSP [0] theory. We will do this by studying the MSP [0 , 1] theory and the [1] theory, which is similar to the argument used to prove the polynomiality of the [0 , 1] theory [Lei24a, Theorem 4.1]. We will first describe a bipartite graph decomposition of the [0 , 1] theory, then prove the polynomiality of the [1] theory. After some work, we will apply the polynomiality of the [1] theory and of the [0 , 1] theory to deduce the polynomiality of the [0] theory.

Definition 2.6. Define G [0 , 1] g,n to be the set of stable bipartite graphs of total genus g and n legs. These are stable graphs with a partition V = V 0 ⊔ V 1 making the graph bipartite.

Theorem 2.7. There is a decomposition of the MSP [0 , 1] theory in terms of stable bipartite graphs as

[[FORMULA_UNAVAILABLE]]

where we define

[[FORMULA_UNAVAILABLE]]

Proof. Recall that the edge contribution in the definition of the MSP [0 , 1] theory is given by

[[FORMULA_UNAVAILABLE]]

The result then follows from the definition of the R -matrix action as a sum over stable graphs. □

- 2.3. Polynomiality of the [1] theory. Recall that we defined the edge contributions to the [0 , 1] theory by

[[FORMULA_UNAVAILABLE]]

Lemma 2.8. Let m,n ≥ 0 , a = 0 , . . . , N +3 , and α, β ∈ { 1 , . . . , N } . In [Lei24a, § 5.3], we defined

[[FORMULA_UNAVAILABLE]]

Then

- (1) ( R m ) α a is independent of α and ( R m ) α a ∈ Q [ X ] m + ⌊ a N ⌋ ;
- (2) The V -bivector has the form

[[FORMULA_UNAVAILABLE]]

where ( V mn ) αβ ; s ∈ Q [ X ] m + n +1 is independent of α, β .

Proof. Note that (1) is [Lei24a, Lemma 5.9]. The proof of (2) is the same as [CGL21, Lemma C.1]. □

Definition 2.9. When ⋆ is either [0], [1], or [0 , 1], define

[[FORMULA_UNAVAILABLE]]

and the [1] theory with special insertions

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

for a ∈ { 0 , . . . , N +3 } n , a ′ ∈ { 1 , . . . , N } m , b ∈ Z n ≥ 0 , and b ′ ∈ Z m ≥ 0 . Here, we define ¯ ϕ a := L -N +3 2 L a p a | H 1 = ∑ N α =1 L a α ¯ 1 α .

Definition 2.10. For a tuple a ∈ Z n ≥ 0 , define | a | := ∑ n i =1 a i and ⌊ a N ⌋ := ∑ n i =1 ⌊ a i N ⌋ .

Lemma 2.11. Let N ≫ 3 g -3 + n + m . Define

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

is a polynomial in X of degree at most 3 g -3 + n + m -| b | - | b ′ | + ⌊ a N ⌋ . Otherwise, f [1] g, ( a , b ) , ( a ′ , b ′ ) = 0 .

If c ∈ Z , then Proof. Recall that f [1] g, ( a , b ) , ( a ′ , b ′ ) is defined as a sum of stable graph contributions, where the contribution from any stable graph is computed as follows:

- (1) At every leg with insertion ϕ a ψ b , we place

[[FORMULA_UNAVAILABLE]]

- (2) At every leg with special insertion R ( ψ ′ ) ¯ ϕ a ′ ψ b ′ , we place

[[FORMULA_UNAVAILABLE]]

- (3) At every edge, we place the bivector 4

[[FORMULA_UNAVAILABLE]]

- (4) At every vertex of genus g v with n v legs, we place the map

[[FORMULA_UNAVAILABLE]]

where

[[FORMULA_UNAVAILABLE]]

was defined in [Lei24a, Theorem 3.6] and st s : M g,n + s → M g,n is the morphism forgetting the last s marked points. Recall from [Lei24a, Lemma 2.4] that

[[FORMULA_UNAVAILABLE]]

We will now count the degrees of the contributions at each vertex labeled by pt α . Let L v be the set of ordinary (first n ) legs attached to v and L ′ v be the set of special legs attached to v . The factor involving L α , L , and Y is

[[FORMULA_UNAVAILABLE]]

Using the fact that

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

the contribution becomes

[[FORMULA_UNAVAILABLE]]

4 Note that we reindex the sum from Lemma 2.8.

The remaining tail, edge, and leg contributions contribute a degree in X of at most

[[FORMULA_UNAVAILABLE]]

Note that the end result must be independent of the hours α , so we can sum over all α and obtain a multiplicative factor

[[FORMULA_UNAVAILABLE]]

Denote the exponent by c v . Clearly if this is not an integer, the contribution vanishes after summing over all α . By our choice of indexing of the edge contributions, we see that s ( e,v 1 ) + s ( e,v 2 ) = 0 whenever e = ( v 1 , v 2 ). In particular, taking the product over all vertices gives an exponent of

[[FORMULA_UNAVAILABLE]]

If this is not an integer, the total contribution vanishes.

Multiplying the prefactors over all vertices, we obtain a total prefactor

[[FORMULA_UNAVAILABLE]]

Using the fact that Y = L -N , the prefactor becomes

[[FORMULA_UNAVAILABLE]]

Multiplying the remaining contributions from the tails, edges, and legs, the total degree in X is at most

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

The desired result follows after applying the normalization factor ( Y t N ) g -1+ c . □

- 2.4. Vanishing of the [0] theory. We will now study the MSP [0] theory. Unfortunately, we need to factorize the MSP [0] theory to prove the desired polynomiality result, but we will prove a vanishing result similar to the first part of Lemma 2.11.

Definition 2.12. Define the modN degrees by deg φ j = deg ϕ j = j mod N and deg ψ = 1.

Lemma 2.13. R [0] ( z ) preserves the modN degree. If we define ¯ j = j mod N , then

[[FORMULA_UNAVAILABLE]]

5

[[FORMULA_UNAVAILABLE]]

where

[[FORMULA_UNAVAILABLE]]

and A M is given by the formulae

[[FORMULA_UNAVAILABLE]]

and all other entries being zero, where

[[FORMULA_UNAVAILABLE]]

The expression for R [0] ϕ j follows directly. The fact that R [0] preserves the modN degree follows from the fact that

[[FORMULA_UNAVAILABLE]]

for all x ∈ H Z and the fact that both S Z and S M preserve the modN degrees. Here, it is helpful to recall that

[[FORMULA_UNAVAILABLE]]

where we define J b = I b I 0 , J ′ 1 = I 11 , and J ′ 2 = J 1 + DJ 2

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

Proof. Recall that Ω [0] = R [0] . Ω Z, tw is defined by a graph sum formula, where the vertex, edge and leg contributions are given by the following:

- At each leg with insertion ϕ a ψ b , we place R [0] ( -ψ ) ∗ ϕ a ψ b ;
- At each edge, we place the bivector

[[FORMULA_UNAVAILABLE]]

5 These are in fact the q coefficients of the quantities I 0 , I 0 I 11 , I 0 I 11 I 22 , and I 2 0 I 11 I 22 .

[[FORMULA_UNAVAILABLE]]

Proof. Recall that

- At each vertex, we place the linear map I 0 ( q ′ ) -(2 g -2+ n ) Ω Z, tw ,τ Z ( q ′ ) g,n ( -).

Because ϕ j ⊗ ϕ j has modN degree 3 and R [0] preserves the modN degree, we see that the edge contributions have modN degree 2. Then note that for · being either ' Z ' or ' Z, tw' the integral

[[FORMULA_UNAVAILABLE]]

vanishes unless ∑ m j =1 ( a j + b j ) = m . Summing over all vertices and edges in an arbitrary stable graph, we see that the contribution can only be nonzero if

which is equivalent to c ∈ Z .

[[FORMULA_UNAVAILABLE]]

We may now assume that c := 1 N ( | a | + | b | -n ) is an integer.

Lemma 2.15. Define

[[FORMULA_UNAVAILABLE]]

If N ≫ 3 g -3 + 3 n , we always have ¯ c ≥ 0 . In addition, if ¯ c = 0 , then f [0] g, ( a , b ) = 0 .

̸

Proof. Using the assumption that N &gt; 3 g -3 + 3 n and the fact that M g,n is a DM stack (hence 3 g -3 + n ≥ 0), we obtain N &gt; 2 n . Because all a i , b i ≥ 0 and ¯ c is an integer, we must have

[[FORMULA_UNAVAILABLE]]

The vanishing result is another degree-counting argument. Assume that ¯ c &gt; 0. Recall f [0] g, ( a , b ) is a sum of stable graph contributions, where we place

[[FORMULA_UNAVAILABLE]]

at the i -th leg. In particular, the total degree of the ancestors is at least

[[FORMULA_UNAVAILABLE]]

However, the contribution vanishes if

[[FORMULA_UNAVAILABLE]]

and therefore if

[[FORMULA_UNAVAILABLE]]

However, by assumption, we see that

[[FORMULA_UNAVAILABLE]]

so all graph contributions must vanish.

□

Corollary 2.16. If f [0] g, ( a , b ) is nonzero, then c = ⌊ a N ⌋ and

[[FORMULA_UNAVAILABLE]]

Definition 2.17. Define the MSP [0] potential with special insertions by

[[FORMULA_UNAVAILABLE]]

where we define

[[FORMULA_UNAVAILABLE]]

Here, [ w b ′ ] means that we take the coefficient of w b ′ in the expression.

By construction, we have

[[FORMULA_UNAVAILABLE]]

Lemma 2.18. If a -m ̸≡ b (mod N ) , then ( ϕ a , R m ¯ ϕ b ) = 0 . In the case when a -m ≡ b (mod N ) , then

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

The result follows by using Lemma 2.8 and the the fact that the total power of the roots of unity is a -m -b . □

Lemma 2.19. The [0] potential with special insertions f [0] g, ( a , b ) , ( a ′ , b ′ ) vanishes unless c := | a | + | b | + | a ′ | + | b ′ | -n + m ∈ Z .

Proof. Write

[[FORMULA_UNAVAILABLE]]

Proof. Note that

[[FORMULA_UNAVAILABLE]]

By the previous lemma, the only nonzero terms are the ones with s ≡ m + b ( (mod N )), so the modN degree of R m ¯ ϕ b is 3 -( m + b ). This implies that the modN degree of E ab is 2 -( a + b ). Computing the total ancestor degree at all vertices as in the proof of Lemma 2.15, we obtain the desired result. □

## 3. The A -model Feynman rule

In order to extract information from the [0] theory, we will extract a part of it which satisfies an X -polynomiality property.

## 3.1. Factorization of the [0] theory.

Definition 3.1. Define the CohFT 6 Ω A , G by the formula

[[FORMULA_UNAVAILABLE]]

Also, define the generating function

[[FORMULA_UNAVAILABLE]]

Remark 3.2 . Because the CohFT Ω Z and Ω A have different units, the graph sum formula for the R A action will have T = z (1 -I 0 ), which by the dilaton equation will imply that we place the linear map

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

at each vertex.

Remark 3.3 . Because the basis φ 0 , . . . , φ 3 is not flat, we will need to consider the transformation

from this basis to the flat basis 1 , H, H 2 , H 3 . In particular, if we want to compute derivatives of R A , G , then we will need the input basis to be the flat basis, and in this basis R A , G ( z ) -1 takes the form

[[FORMULA_UNAVAILABLE]]

Definition 3.4. Define the matrix

[[FORMULA_UNAVAILABLE]]

We will consider the input basis of R X to be φ 0 , . . . , φ 3 and the output basis to be ϕ 0 , . . . , ϕ N +3 .

Lemma 3.5. The matrix elements ( R X m ) a j := ( ϕ j , R X m φ a ) of R X satisfy the following whenever m&lt;N -3 :

- (1) If j ̸≡ m + a (mod N ) , then ( R X m ) a j = 0 ;
- (2) If j &lt; N , then ( R X m ) a j ∈ X Q [ X ] m -1 ;
- (3) If j ≥ N , then ( R X m ) a j ∈ q Q [ X ] m ;
- (4) We have R X ( -z ) ∗ C X ( z ) = Id H Z for some C X ( z ) of the form ( C ( z ) 0 ) , where C ( z ) has the form

[[FORMULA_UNAVAILABLE]]

for some C 1 , C 2 , C 4 , C 6 ∈ Q [ X ] 1 and C 3 , C 5 ∈ Q [ X ] 2 .

6 Note that the unit of this CohFT is φ 0 and not 1.

Proof. Using the equation

[[FORMULA_UNAVAILABLE]]

Using the definition R [0] ( z ) ∗ = R A ( z ) ∗ R X ( z ) ∗ , we obtain

[[FORMULA_UNAVAILABLE]]

and multiplying by R A ( -z ), we obtain

[[FORMULA_UNAVAILABLE]]

Direct computation (here, note that the basis φ 0 , . . . , φ 3 is not flat, so we need the version of R A with the Ψ) yields

[[FORMULA_UNAVAILABLE]]

Therefore, we can compute R X ( z ) ∗ ϕ i from R X ( z ) ∗ ϕ 0 . Because R [0] ( z ) ∗ ϕ 0 = φ 0 + O ( z N -3 ) and R A ( z ) ∗ φ 0 = φ 0 , the first entry of R X is 1 + O ( z N -3 ).

We then note that the matrices A M and R A ( -z )[( zD + A Z ) R A ( z ) ∗ ] both increase the modN degree by 1. Therefore, we see that R X preserves the modN degree, so the vanishing property holds. The degree estimates follow from the explicit formulae for A M and R A ( -z )[( zD + A Z ) R A ( z ) ∗ ]. The final statement is obtained by direct computation. □

Corollary 3.6. The edge contribution

[[FORMULA_UNAVAILABLE]]

satisfies the degree bound

[[FORMULA_UNAVAILABLE]]

Proof. This follows from the lemma and the fact that φ j = t N p k Y φ 3 -j . □

- 3.2. Polynomiality of the [0] theory and the A theory. We now prove the polynomiality of the [0]-theory. First, we will prove some lemmas about E a ′ ,b ′ ( z ), which was introduced in Definition 2.17.

Lemma 3.7. Recall the definition of E a ′ ,b ′ ( z ) from Definition 2.17. Then

[[FORMULA_UNAVAILABLE]]

unless a + a ′ + b + b ′ ≡ 2 (mod N ) .

Proof. By definition, we have

[[FORMULA_UNAVAILABLE]]

which vanishes unless a -a ′ -( b + b ′ +1) ≡ 0 (mod N ). The result follows from the fact that ϕ a has modN degree 3 -a . □

Lemma 3.8. Whenever N ≫ b ′′ , then

[[FORMULA_UNAVAILABLE]]

where we define c E := a ′ + b ′ + a ′′ + b ′′ -N -2 N . If c E / ∈ Z , then the above quantity vanishes.

Proof. The vanishing is a corollary of Lemma 3.5 and Lemma 3.7. The degree estimate comes from the following considerations.

Whenever a = 4 , . . . , N -1 and m ′ &lt; N -3, then ( φ a ′′ , [ z m ′ ] R X ( -z ) ∗ ϕ a ) is nonzero only if a = a ′′ + m ′ . If this is satisfied, then it has degree m ′ in X , and therefore

[[FORMULA_UNAVAILABLE]]

Here, we use the fact that

[[FORMULA_UNAVAILABLE]]

by Lemma 2.8 because ⌊ a N ⌋ = 0.

In the case where a = 0 , . . . , 3, then for any m ′ &lt; N -3, the vanishing still holds, so we use ϕ a = 1 5 ( ϕ N +3 -a -t N ϕ 3 -a ) to compute. The ϕ N +3 -a term contributes an element of Q [ X ] b ′ + b ′′ +2 , whereas the t N ϕ 3 -a term contributes

[[FORMULA_UNAVAILABLE]]

Therefore, we have

[[FORMULA_UNAVAILABLE]]

In the case when a ≥ N , the nonvanishing condition becomes a -N = a ′′ + m ′ . Therefore, Lemma 3.5 implies that

[[FORMULA_UNAVAILABLE]]

If we sum the contributions from the above procedure, the degree count is too high by 1. The X b ′ + b ′′ +2 -coefficient is given by (up to a constant)

[[FORMULA_UNAVAILABLE]]

Note that the MSP quantum connection (3.1) (in particular the value of A M ) implies that [ X m +1 ]( R m ) j = c ′ j,k r · [ X m ]( R m ) j -N and the equation (3.2) for R X implies that [ X m ]( q -1 ( R X m ) a j ) = c ′ j,k · [ X m ]( R m ) a j -N , where c ′ j,k was defined in Lemma 2.13.

This implies that

[[FORMULA_UNAVAILABLE]]

for all i + j = b ′ + b ′′ + 1 and a = 0 , 1 , 2 , 3, where we have used the fact that c ′ N + a + c ′ N +3 -a = -r , which is implied by the fact that I 2 0 I 2 11 I 22 = Y . □

We will now put a partial ordering on the set of pairs ( g, n ) such that ( h, m ) ≺ ( g, n ) if ( h, m ) &lt; ( g, n ) in the lexicographic order and 3 h + m ≤ 3 g + n . We will use induction on ( h, m ) under this ordering and a bootstrapping argument to prove both the polynomiality of the [0] theory and of the A theory.

We introduce the following statements:

- (1) Denote by P g,n the statement 'for all a ∈ { 0 , 1 , 2 , 3 } n and b ∈ Z n ≥ 0 , we have

[[FORMULA_UNAVAILABLE]]

- (2) Denote by Q g,s the statement 'for all m + n ≤ s , a ∈ { 0 , . . . , N + 3 } m , ( b , b ′ ) ∈ Z m + n ≥ 0 , and a ′ ∈ { 1 , . . . , N } n ,

[[FORMULA_UNAVAILABLE]]

Lemma 3.9. Suppose that P h,m holds for all ( h, m ) ≺ ( g, n ) . Then for all ( h, m ) ≺ ( g, n ) , we have

[[FORMULA_UNAVAILABLE]]

for all a ∈ { 0 , 1 , 2 , 3 } m .

Proof. First, note that R A preserves degrees, so we must have ∑ i ( a i + b i ) = n . Now define

[[FORMULA_UNAVAILABLE]]

By the assumption P h,m and the fact that C X has nonzero entries only in the top four rows, preserves the modN degree, and the fact that ( ϕ j , C X ℓ φ a ) ∈ Q [ X ] ℓ , we see that

[[FORMULA_UNAVAILABLE]]

In the graph sum formula for the action of R X and Ω A , we see there is a graph with a single genus h vertex with m insertions (corresponding to the largest stratum of M h,m ). The contribution of this graph is f A h, ( a , b ) . The contribution of any other graph will have the form

[[FORMULA_UNAVAILABLE]]

where V X ( e ) was defined in Corollary 3.6.

We will now induct on ( h, m ). In the base case ( h, m ) = (0 , 3), the leading graph is the only graph, so the result follows directly (note here the different normalization conventions for f A and f [0] ). Now we assume the result for all ( h ′ , m ′ ) ≺ ( h, m ). Using the graph sum, we now count the degrees of all of the contributions.

- The total exponent of Y t N is ∑ v ( g v -1) + | E | = h -1 using Corollary 3.6 and distributing the factors of Y as in the proof of [Lei24a, Theorem 6.1];
- The total degree in X is at most

[[FORMULA_UNAVAILABLE]]

Lemma 3.10. If P h,m holds for all ( h, m ) ≺ ( g, n ) , then Q h,m also holds for all ( h, s ) ≺ ( g, n ) .

Proof. Recall that Ω [0] = R X . Ω A . This implies that f [0] h, ( a , b ) , ( a ′ , b ′ ) can be written as a graph sum, where the contribution of a stable graph Γ is given by the following:

- For each ordinary leg ℓ , we insert R X ( -ψ ) ∗ ϕ a ψ b . By Lemma 3.5, this in fact becomes

[[FORMULA_UNAVAILABLE]]

for a unique m ℓ (here, note that the ancestor degree must be at most 3 g v -3 + n v &lt; N ).

- For each special leg ℓ ′ , we insert R X ( -ψ ) ∗ E a ′ ,b ′ ( ψ ). Using Lemma 3.7 and Lemma 3.8, this becomes

[[FORMULA_UNAVAILABLE]]

for a unique a ′′ , b ′′ .

- At every edge, we insert the bivector V X .

We now consider the total degree of the contributions from a graph Γ.

- The total exponent of Y t N is given by

[[FORMULA_UNAVAILABLE]]

Using the fact that

[[FORMULA_UNAVAILABLE]]

by Corollary 3.6, we obtain

[[FORMULA_UNAVAILABLE]]

which implies that the total exponent is -( c + n + h -1).

- The total degree in X is at most

[[FORMULA_UNAVAILABLE]]

Theorem 3.11. For all a , b ∈ { 0 , . . . , N +3 } n , we have

[[FORMULA_UNAVAILABLE]]

Proof. We will induct on ( g, n ) under the ordering ≺ . The base case is ( g, n ) = (0 , 3). In this case, there is only one graph with a single vertex. Because dim M g,n = 0, no ancestor insertions are allowed, and so we calculate

[[FORMULA_UNAVAILABLE]]

Here, we use the fact that c = ⌊ a N ⌋ and the computation of genus-zero three-point functions in [Lei24a, § 2.4].

We now assume the desired polynomiality result for ( h, m ) ≺ ( g, n ). This implies P h,m and thus Q h,m for all ( h, m ) ≺ ( g, n ) by Lemma 3.10. We may also assume that c = ⌊ a N ⌋ by Corollary 2.16.

We will now consider the [0 , 1] theory. By [Lei24a, Theorem 4.1], f [0 , 1] g, ( a , b ) is a polynomial in q of degree at most g -1 + 3 g -3+ | a | N . By Lemma 2.15, this becomes

[[FORMULA_UNAVAILABLE]]

Because 0 ≤ | b | ≤ 3 g -3 + n and N ≫ 3 g -3 + n , we see that the degree is in fact at most g -1 + c . Multiplying by ( Y t N ) g -1+ c , we see that

[[FORMULA_UNAVAILABLE]]

By Corollary 2.16, this satisfies the desired degree bound.

We will now apply the bipartite graph decomposition from Theorem 2.7. There is a leading bipartite graph with only a single level 0 vertex. We need to prove the degree estimate for the non-leading graphs. Applying Q h,m at level 0 and Lemma 2.11 at level 1, we now count the total degree contribution of a bipartite graph Λ.

- The total exponent of Y t N is

[[FORMULA_UNAVAILABLE]]

- The total degree in X is

[[FORMULA_UNAVAILABLE]]

Because a stable graph describes a codimension | E | stratum in M g,n , this is at most 3 g -3 + n + ⌊ a N ⌋ -| b | . □

Applying Lemma 3.9, we obtain the following.

Corollary 3.12. For all ( g, n ) such that 2 g -2 + n &gt; 0 , all a ∈ { 0 , 1 , 2 , 3 } n , and all b ∈ Z n ≥ 0 , we have

[[FORMULA_UNAVAILABLE]]

- 3.3. Choice of gauge. Note that

[[FORMULA_UNAVAILABLE]]

where we compute

[[FORMULA_UNAVAILABLE]]

Note that this is a symplectic matrix, so we have an equality

[[FORMULA_UNAVAILABLE]]

of CohFTs.

Theorem 3.13. For all ( g, n ) such that 2 g -2 + n &gt; 0 , all a ∈ { 0 , 1 , 2 , 3 } n , and all b ∈ Z n ≥ 0 , we have

[[FORMULA_UNAVAILABLE]]

Proof. We will write the stable graph sum formula for Ω A , G as the G -action on Ω A . The contribution of a stable graph Γ is given by the following assignments:

- At each leg, we place G ( -z ) ∗ φ a ψ b = ∑ m G ∗ m ( -ψ ) m φ a ψ b ;
- At each edge, we place

[[FORMULA_UNAVAILABLE]]

Here, note that G ∗ m has degree m in X and V ab has degree a + b + a in X by the assumption on the gauge in Definition 1.6.

We now compute the total degree of the contribution. The total exponent of Y t N in the contribution of Γ to Ω A , G g,n is

[[FORMULA_UNAVAILABLE]]

On the other hand, the total degree in X is at most

[[FORMULA_UNAVAILABLE]]

## 4. The B-model Feynman rule

In this section, we will define the B-model Feynman rule and prove that it equals the A-model Feynman rule. From now on, we will make the specialization t N = -1. This makes q ′ = q and makes

[[FORMULA_UNAVAILABLE]]

Convention 4.1. In this section, we will omit all superscripts of G , so E ∗∗ stands for E G ∗∗ , R A stands for R A , G , and so on.

4.1. B-model geometric quantization. We will first express the physics Feynman rule using geometric quantization. Note that the Givental formalism is a type of geometric quantization, so we will be able to compare the A-model and B-model quantizations.

Consider the vector space

[[FORMULA_UNAVAILABLE]]

with the symplectic form

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

Because H S is a symplectic vector space, we will write elements as

[[FORMULA_UNAVAILABLE]]

Definition 4.2. Following [CPS18], we define the geometric quantization ̂ R B by the Gaussian integral

[[FORMULA_UNAVAILABLE]]

Here, Q ( x ′ , p ′ ) is defined by the formula

[[FORMULA_UNAVAILABLE]]

and ( p ′ , x ′ ) are coordinates on R 4 = R 2 × R 2 .

Following [CPS18, § 3.4], a standard argument involving the Fourier transform gives us the operator form

[[FORMULA_UNAVAILABLE]]

Now define ˜ E φφ , ˜ E φψ , and ˜ E ψψ by

[[FORMULA_UNAVAILABLE]]

Then define

Then if we define

[[FORMULA_UNAVAILABLE]]

the operator form of the quantization action becomes

[[FORMULA_UNAVAILABLE]]

Definition 4.3. Define the (normalized) Gromov-Witten correlator of Z by the formula

[[FORMULA_UNAVAILABLE]]

̸

when ( g, m ) = (1 , 0) and define

[[FORMULA_UNAVAILABLE]]

Definition 4.4. Define the master B-model Gromov-Witten potential function by

[[FORMULA_UNAVAILABLE]]

Then, define the master B-model potential function by

[[FORMULA_UNAVAILABLE]]

By [CPS18, Theorem 10], we can also compute f B by the construction in Definition 1.8.

4.2. Factorization of the quantization action. We will factor the quantization action (4.1) into the change of variables and the application of differential operators. Observe that D -1 x = ( x, y -E ψ x ). Then the transformation

[[FORMULA_UNAVAILABLE]]

is given by quantizing the matrix

[[FORMULA_UNAVAILABLE]]

Then we compute

[[FORMULA_UNAVAILABLE]]

where

[[FORMULA_UNAVAILABLE]]

We then compute

[[FORMULA_UNAVAILABLE]]

so we see that f B ( ℏ , x, y ) = ̂ ˜ R B ˜ P B ( ℏ , x, y ).

4.3. Modification of the A-model quantization. Note that in the graph sum formula for Ω A , the edge contribution is given by

[[FORMULA_UNAVAILABLE]]

In order to prove that the A-model and B-model Feynman rules are equivalent, we need to analyze the contributions of the three extra terms. We will begin with the terms E ψ ( φ 0 ⊗ φ 2 + φ 2 ⊗ φ 0 ) and study a parallel construction to the modified B-model quantization.

The parallel construction in the A-model is to consider the matrix 7

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

Recall that matrices are written in the basis φ 0 , φ 1 , φ 2 , φ 3 .

Definition 4.5. Define the CohFT

[[FORMULA_UNAVAILABLE]]

and the factorization

and the potential

[[FORMULA_UNAVAILABLE]]

for the coordinate

[[FORMULA_UNAVAILABLE]]

Specializing to the case t = ( x , 0), we define

[[FORMULA_UNAVAILABLE]]

Lemma 4.6. We have the identity

[[FORMULA_UNAVAILABLE]]

Proof. By [Lee09, Theorem 5], the R -matrix action preserves all tautological equations on the moduli spaces of curves, in particular the string and dilaton equations, so we can apply the dilaton equation to ˜ Ω Z . We also note that changing ˜ P B ( ℏ , x, y ) to ˜ P B ( ℏ , x, y ) is the same as replacing P 1 , 0 ,n by the actual Gromov-Witten invariant

[[FORMULA_UNAVAILABLE]]

7 This should also implicitly have a Ψ -1 on the right, but we will omit it.

so applying the dilaton equation to both sides (where ˜ P denotes either ˜ P A or ˜ P B ) yields

̸

[[FORMULA_UNAVAILABLE]]

Therefore, we only need to prove that ˜ P A ( ℏ , x, 0) = ˜ P B ( ℏ , x, 0).

We will now consider the graph sum formula for the definition of ˜ Ω Z . The edge contributions are given by E ψ ( φ 0 ⊗ φ 2 + φ 2 ⊗ φ 0 ). All insertions at legs are E A ( -ψ ) ∗ φ 1 = φ 1 -E ψ φ 0 ψ , and each vertex contributes a Gromov-Witten correlator of Z . Applying the string equation, dilaton equation, divisor equation, and virtual dimension constraints, if the stable graph Γ has at least one edge and one vertex of g &gt; 0, then its contribution vanishes. By a similar argument, any vertex with more than two edges has vanishing contribution. Therefore, we have a decomposition

[[FORMULA_UNAVAILABLE]]

where the first term comes from the leading graphs with a single genus g vertex and the second comes from loops of genus zero vertices, which contribute to the genus 1 potential. Every vertex must have at least one φ 1 insertion by dimension reasons, and the string and dilaton equations imply that there is exactly one φ 1 insertion. Therefore, we use the dilaton equation to remove the -E ψ φ 0 ψ insertions and compute

[[FORMULA_UNAVAILABLE]]

Here, we have used the following combinatorial facts:

- There are ( m -1)! ways to arrange m vertices in a loop;
- For any partition n = n 1 + · · · + n m of the φ 0 ψ insertions, the number of possible assignments is n ! n 1 ! ··· n m ! ;

- Applying the dilaton equation to any vertex with n i insertions of φ 0 ψ and one insertion of φ 1 produces a factor of n !.

We conclude that

[[FORMULA_UNAVAILABLE]]

- 4.4. Equality of A-model and B-model potentials. A direct computation yields

[[FORMULA_UNAVAILABLE]]

By [Giv01, Proposition 7.3], we see that

[[FORMULA_UNAVAILABLE]]

where

[[FORMULA_UNAVAILABLE]]

We will first prove some technical lemmas about the geometric quantization formalism. This is

## Lemma 4.7. We have the equality

[[FORMULA_UNAVAILABLE]]

Proof. The operator form of the string equation 8 is

[[FORMULA_UNAVAILABLE]]

By virtual dimension reasons, we obtain the initial condition

[[FORMULA_UNAVAILABLE]]

8 If we write φ ( z ) = ∑ 3 i =0 t j i φ i z j , the operator form of the string equation (see [Giv04]) is

[[FORMULA_UNAVAILABLE]]

Because there are no φ 2 or φ 3 insertions, the unstable term disappears. We then set t 0 1 = x , t 1 1 = a , t 0 0 = c , t 1 0 = y , and t 2 0 = b . Here, D = e ˜ P A .

The desired result follows from the computation

[[FORMULA_UNAVAILABLE]]

Theorem 4.8. We have the equality

[[FORMULA_UNAVAILABLE]]

Proof. Our goal is to compute the function

[[FORMULA_UNAVAILABLE]]

We will first consider the contribution of c 1 -y ( a ∂ ∂x + b ∂ ∂y ) and V extra ( ∂ t , ∂ t ). For any function D ( x, y ), we compute

[[FORMULA_UNAVAILABLE]]

Now set E extra ( ∂ t ) := -ℏ 1 -y ( ˜ E φψ ∂ ∂x + ˜ E ψψ ∂ ∂y ) .

To deal with the contribution of V B ( ∂ t , ∂ t ), we compute

[[FORMULA_UNAVAILABLE]]

Dividing by 1 -y , we see that

[[FORMULA_UNAVAILABLE]]

or in other words that

[[FORMULA_UNAVAILABLE]]

Putting all of this together, we see that

[[FORMULA_UNAVAILABLE]]

The desired result follows by taking logarithms.

Corollary 4.9 (B-model Feynman rule) . For any g, m, n , we have

[[FORMULA_UNAVAILABLE]]

Proof. By Theorem 4.8, we see that f A g,m,n = f B g,m,n + δ g, 1 δ m, 0 ( n -1)!. The result then follows from Corollary 3.12 by choosing a = (1 m 0 n ) and b = (0 n 1 m ). □

## 5. Anomaly equations

Our goal is to prove the following theorem.

Theorem 5.1. The P g,m satisfy the differential equations

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

□

In order to prove this, we introduce a smaller ring of modified generators which contains the P g .

Definition 5.2. Define the modified generators

[[FORMULA_UNAVAILABLE]]

and then set

[[FORMULA_UNAVAILABLE]]

Remark 5.3 . The ring ˜ R is in fact invariant under the choice of gauge. Direct computation yields

[[FORMULA_UNAVAILABLE]]

so we will write the generators with no superscript and G = 0 . Here, recall that c 11 , c 12 , c 2 , c 3 ∈ Q [ X ].

Remark 5.4 . Our generators are related to the generators v 1 , v 2 , and v 3 introduced in [YY04] by the formulae

[[FORMULA_UNAVAILABLE]]

Lemma 5.5. The ring ˜ R is closed under the derivative D .

Proof. A direct computation yields

[[FORMULA_UNAVAILABLE]]

Theorem 5.6 (Reduction of generators) . Let g &gt; 1 . Then P g ∈ ˜ R .

Proof. First, note that by definition, we have P g = ˜ P g . We will now prove that all ˜ P g,m ∈ ˜ R by induction on the lexicographic order in ( g, m ). Recall that f B g,m can be computed from ˜ P B h ≤ g,m,n by the geometric quantization of R B . The contribution of each stable graph to this quantization is given by the following construction:

- At each leg, we place φ 1 or φ 0 ψ ;
- At every edge, we place the bivector

[[FORMULA_UNAVAILABLE]]

- At every vertex, we place the linear map φ ⊗ m 1 ⊗ ( φ 0 ψ ) ⊗ n ↦→ ˜ P g,m,n .

The base cases are ˜ P 1 , 0 , 1 = χ ( Z ) 24 -1 and ˜ P 0 , 3 = 1. The dilaton equation implies that if ˜ P g,m ∈ ˜ R , then ˜ P g,m,n ∈ ˜ R for all n . Now we assume that ˜ P h,ℓ,n ∈ ˜ R for all ( h, ℓ ) &lt; ( g, m ). Then we know f B g,m ∈ Q [ X ] by Corollary 4.9. Computing it by the stable graph sum, we see

[[FORMULA_UNAVAILABLE]]

By the inductive hypothesis and the formula for the edge contributions, Cont Γ ∈ ˜ R for any non-leading Γ. The desired result follows immediately. □

Proof of Theorem 5.1. The second equation (5.2) is equivalent to Theorem 5.6 by the results of [YY04], so we only need to prove (5.1). We proceed by differentiating the quantization action. By definition, we have

[[FORMULA_UNAVAILABLE]]

Applying ∂ being either ∂ A , ∂ B , ∂ B 2 , or ∂ B 3 , we see that

[[FORMULA_UNAVAILABLE]]

Making the change of variables t ′ = ( x ′ , y ′ ) := ( x, y -E ψ x ), we then see that

[[FORMULA_UNAVAILABLE]]

From now on, we will replace x ′ by x and y ′ by y for simplicity. We now see that

[[FORMULA_UNAVAILABLE]]

First, ∂ A V B , small ( ∂ t , ∂ t ) = 1 2 ∂ 2 ∂x 2 , so we obtain

[[FORMULA_UNAVAILABLE]]

Setting x = y = 0, we see that

[[FORMULA_UNAVAILABLE]]

Taking the coefficient of ℏ

g -1 on both sides, we obtain (5.1). □

## References

- [BCOV94] M. Bershadsky, S. Cecotti, H. Ooguri, and C. Vafa. 'Kodaira-Spencer theory of gravity and exact results for quantum string amplitudes'. In: Comm. Math. Phys. 165.2 (1994), pp. 311-427. issn : 0010-3616,14320916.
- [Beh97] K. Behrend. 'Gromov-Witten invariants in algebraic geometry'. In: Invent. Math. 127.3 (1997), pp. 601-617. issn : 0020-9910,1432-1297. doi : 10.1007/s002220050132 .
- [BF97] K. Behrend and B. Fantechi. 'The intrinsic normal cone'. In: Invent. Math. 128.1 (1997), pp. 45-88. issn : 0020-9910,1432-1297. doi : 10.100 7/s002220050136 .
- [CCK15] Daewoong Cheong, Ionut ¸ Ciocan-Fontanine, and Bumsig Kim. 'Orbifold quasimap theory'. In: Math. Ann. 363.3-4 (2015), pp. 777-816. issn : 0025-5831,1432-1807. doi : 10.1007/s00208-015-1186-z .
- [CCLT09] Tom Coates, Alessio Corti, Yuan-Pin Lee, and Hsian-Hua Tseng. 'The quantum orbifold cohomology of weighted projective spaces'. In: Acta Math. 202.2 (2009), pp. 139-193. issn : 0001-5962,1871-2509. doi : 10.1 007/s11511-009-0035-x .

- [CG07] Tom Coates and Alexander Givental. 'Quantum Riemann-Roch, Lefschetz and Serre'. In: Ann. of Math. (2) 165.1 (2007), pp. 15-53. issn : 0003-486X,1939-8980. doi : 10.4007/annals.2007.165.15 .
- [CGL19] Huai-Liang Chang, Shuai Guo, and Jun Li. BCOV's Feynman rule of quintic 3 -folds . 2019. arXiv: 1810.00394 .
- [CGL21] Huai-Liang Chang, Shuai Guo, and Jun Li. 'Polynomial structure of Gromov-Witten potential of quintic 3-folds'. In: Ann. of Math. (2) 194.3 (2021), pp. 585-645. issn : 0003-486X,1939-8980. doi : 10.4007/a nnals.2021.194.3.1 .
- [CGLL21] Huai-Liang Chang, Shuai Guo, Jun Li, and Wei-Ping Li. 'The theory of N -mixed-spinP fi elds'. In: Geom. Topol. 25.2 (2021), pp. 775-811. issn : 1465-3060,1364-0380. doi : 10.2140/gt.2021.25.775 .
- [CL20] Huai-Liang Chang and Jun Li. 'A vanishing associated with irregular MSP fields'. In: Int. Math. Res. Not. IMRN 20 (2020), pp. 7347-7396. issn : 1073-7928,1687-0247. doi : 10.1093/imrn/rnaa049 .
- [CLLL19] Huai-Liang Chang, Jun Li, Wei-Ping Li, and Melissa Chiu-Chu Liu. 'Mixed-Spin-P fields of Fermat polynomials'. In: Cambridge Journal of Mathematics 7.3 (2019), pp. 319-364. issn : 2168-0930. doi : 10.4310 /CJM.2019.v7.n3.a3 .
- [CLLL22] Huai-Liang Chang, Jun Li, Wei-Ping Li, and Chiu-Chu Melissa Liu. 'An effective theory of GW and FJRW invariants of quintic Calabi-Yau manifolds'. In: J. Differential Geom. 120.2 (2022), pp. 251-306. issn : 0022-040X,1945-743X. doi : 10.4310/jdg/1645207466 .
- [COGP92] Philip Candelas, Xenia C. de la Ossa, Paul S. Green, and Linda Parkes. 'A pair of Calabi-Yau manifolds as an exactly soluble superconformal theory'. In: Essays on mirror manifolds . Int. Press, Hong Kong, 1992, pp. 31-95. isbn : 962-7670-01-4.
- [CPS18] Emily Clader, Nathan Priddis, and Mark Shoemaker. 'Geometric quantization with applications to Gromov-Witten theory'. In: B-model Gromov-Witten theory . Trends Math. Birkh¨ auser/Springer, Cham, 2018, pp. 399-462. isbn : 978-3-319-94219-3; 978-3-319-94220-9.
- [FO99] Kenji Fukaya and Kaoru Ono. 'Arnold conjecture and Gromov-Witten invariant'. In: Topology 38.5 (1999), pp. 933-1048. issn : 0040-9383. doi : 10.1016/S0040-9383(98)00042-1 .
- [FP00] C. Faber and R. Pandharipande. 'Hodge integrals and Gromov-Witten theory'. In: Invent. Math. 139.1 (2000), pp. 173-199. issn : 00209910,1432-1297. doi : 10.1007/s002229900028 .
- [Giv01] Alexander B. Givental. 'Gromov-Witten invariants and quantization of quadratic Hamiltonians'. In: vol. 1. 4. Dedicated to the memory of I. G. Petrovskii on the occasion of his 100th anniversary. 2001, pp. 551-568, 645. doi : 10.17323/1609-4514-2001-1-4-551-568 .
- [Giv04] Alexander B. Givental. 'Symplectic geometry of Frobenius structures'. In: Frobenius manifolds . Vol. E36. Aspects Math. Friedr. Vieweg, Wiesbaden, 2004, pp. 91-112. isbn : 3-528-03206-5.
- [Giv96] Alexander B. Givental. 'Equivariant Gromov-Witten invariants'. In: Internat. Math. Res. Notices 13 (1996), pp. 613-663. issn : 1073-7928,16870247. doi : 10.1155/S1073792896000414 .

- [GJR17] Shuai Guo, Felix Janda, and Yongbin Ruan. A mirror theorem for genus two Gromov-Witten invariants of quintic threefolds . 2017. arXiv: 1709.07392 .
- [GJR18] Shuai Guo, Felix Janda, and Yongbin Ruan. Structure of Higher Genus Gromov-Witten Invariants of Quintic 3-folds . 2018. arXiv: 1812.11908 .
- [HKQ09] M.-x. Huang, A. Klemm, and S. Quackenbush. 'Topological string theory on compact Calabi-Yau: modularity and boundary conditions'. In: Homological mirror symmetry . Vol. 757. Lecture Notes in Phys. Springer, Berlin, 2009, pp. 45-102. isbn : 978-3-540-86374-8.
- [Lee09] Y.-P. Lee. 'Invariance of tautological equations. II. Gromov-Witten theory'. In: J. Amer. Math. Soc. 22.2 (2009). With an appendix by Y. Iwao and the author, pp. 331-352. issn : 0894-0347,1088-6834. doi : 10.1090/S0894-0347-08-00616-4 .
- [Lei24a] Patrick Lei. Higher-genus Gromov-Witten theory of one-parameter Calabi-Yau threefolds I: Polynomiality . 2024. arXiv: 2409.11659 .
- [Lei24b] Patrick Lei. MSP theory for smooth Calabi-Yau threefolds in weighted P 4 . 2024. arXiv: 2409.11660 .
- [LLY97] Bong H. Lian, Kefeng Liu, and Shing-Tung Yau. 'Mirror principle. I'. In: Asian J. Math. 1.4 (1997), pp. 729-763. issn : 1093-6106,1945-0036. doi : 10.4310/AJM.1997.v1.n4.a5 .
- [LT98a] Jun Li and Gang Tian. 'Virtual moduli cycles and Gromov-Witten invariants of algebraic varieties'. In: J. Amer. Math. Soc. 11.1 (1998), pp. 119-174. issn : 0894-0347,1088-6834. doi : 10.1090/S0894-0347-9 8-00250-1 .
- [LT98b] Jun Li and Gang Tian. 'Virtual moduli cycles and Gromov-Witten invariants of general symplectic manifolds'. In: Topics in symplectic 4 -manifolds (Irvine, CA, 1996) . Vol. I. First Int. Press Lect. Ser. Int. Press, Cambridge, MA, 1998, pp. 47-83. isbn : 1-57146-019-5.
- [Pop13] Alexandra Popa. 'The genus one Gromov-Witten invariants of CalabiYau complete intersections'. In: Trans. Amer. Math. Soc. 365.3 (2013), pp. 1149-1181. issn : 0002-9947,1088-6850. doi : 10.1090/S0002-99472012-05550-4 .
- [PPZ15] Rahul Pandharipande, Aaron Pixton, and Dimitri Zvonkine. 'Relations on M g,n via 3-spin structures'. In: J. Amer. Math. Soc. 28.1 (2015), pp. 279-309. issn : 0894-0347,1088-6834. doi : 10.1090/S0894-0347-2 014-00808-0 .
- [RT95] Yongbin Ruan and Gang Tian. 'A mathematical theory of quantum cohomology'. In: J. Differential Geom. 42.2 (1995), pp. 259-367. issn : 0022-040X,1945-743X.
- [Rua99] Yongbin Ruan. 'Virtual neighborhoods and pseudo-holomorphic curves'. In: Proceedings of 6th G¨ okova Geometry-Topology Conference . Vol. 23. 1. 1999, pp. 161-231.
- [Sie98] Bernd Siebert. Gromov-Witten invariants of general symplectic manifolds . 1998. arXiv: dg-ga/9608005 .
- [Wan20] Jun Wang. A mirror theorem for Gromov-Witten theory without convexity . 2020. arXiv: 1910.14440 .

- [YY04] Satoshi Yamaguchi and Shing-Tung Yau. 'Topological string partition functions as polynomials'. In: J. High Energy Phys. 7 (2004), pp. 047, 20. issn : 1126-6708,1029-8479. doi : 10.1088/1126-6708/2004/07/047 .
- [Zho22] Yang Zhou. 'Quasimap wall-crossing for GIT quotients'. In: Invent. Math. 227.2 (2022), pp. 581-660. issn : 0020-9910,1432-1297. doi : 10.1 007/s00222-021-01071-z .
- [Zin09] Aleksey Zinger. 'The reduced genus 1 Gromov-Witten invariants of Calabi-Yau hypersurfaces'. In: J. Amer. Math. Soc. 22.3 (2009), pp. 691737. issn : 0894-0347,1088-6834. doi : 10.1090/S0894-0347-08-00625 -5 .