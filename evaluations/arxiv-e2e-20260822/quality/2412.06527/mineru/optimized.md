# HIGHER GENUS GROMOV-WITTEN THEORY OF ONE-PARAMETER CALABI-YAU THREEFOLDS II: FEYNMAN RULE AND ANOMALY EQUATIONS

## PATRICK LEI

Abstract. We prove the Feynman rule conjectured by Bershadsky-Cecotti-Ooguri-Vafa [BCOV94] and the anomaly equations conjectured by Yamaguchi-Yau [YY04] for the Gromov-Witten theory of the Calabi-Yau threefolds $Z _ { 6 } \subset$ $\mathbb { P } ( 1 , 1 , 1 , 1 , 2 ) , Z _ { 8 } \subset \mathbb { P } ( 1 , 1 , 1 , 1 , 4 )$ , and $Z _ { 1 0 } \subset \mathbb { P } ( 1 , 1 , 1 , 2 , 5 )$ . These determine the generating series $F _ { g }$ of genus g Gromov-Witten invariants recursively from the lower-genus $F _ { h < g }$ up to $3 g - 3$ unknown parameters.

## Contents

1. Introduction 2
1.1. Historical overview 2
1.2. Setup and past work 3
1.3. Feynman rule 4
1.4. Anomaly equations 7
1.5. Outline 7
1.6. Conventions 7
Acknowledgements 8
2. MSP [0] and [1] theories 8
2.1. The MSP [0, 1] theory 8
2.2. The MSP [0] and [1] theories 10
2.3. Polynomiality of the [1] theory 12
2.4. Vanishing of the [0] theory 14
3. The A-model Feynman rule 17
3.1. Factorization of the [0] theory 18
3.2. Polynomiality of the [0] theory and the A theory 19
3.3. Choice of gauge 24
4. The B-model Feynman rule 25
4.1. B-model geometric quantization 26
4.2. Factorization of the quantization action 27
4.3. Modification of the A-model quantization 28
4.4. Equality of A-model and B-model potentials 30
5. Anomaly equations 32
References 34

## 1. Introduction

1.1. Historical overview. Despite its origin in theoretical physics as a duality between A-model and B-model topological string theories, mirror symmetry has sparked significant interest in mathematics, starting with the landmark paper [COGP92], which gave predictions for the number of genus zero curves of any degree on the quintic threefold. Even though their predictions difer from the actual numbers of curves, they sparked a significant change in the field of enumerative geometry – namely, to consider deformation-invariant virtual counts of curves. The first mathematical theory constructed to satisfy this property is Gromov-Witten theory (a formalization of A-model invariants), which was developed in symplectic topology by various authors [RT95; LT98b; Sie98; FO99; Rua99] and in algebraic geometry by Behrend-Fantechi and Li-Tian [BF97; Beh97; LT98a].

For physical reasons, a central problem in Gromov-Witten theory is to compute the Gromov-Witten invariants of compact Calabi-Yau threefolds. For simplicity, we will restrict to the case when $h ^ { 2 } = 1$ and in particlar to those which arise as complete intersections in weighted projective spaces, of which there are 13 examples (see [HKQ09, §4] for a complete list). We will list (very incompletely) some historical developments in mathematics and physics:

• A theorem determining the genus zero invariants generalizing the predictions of [COGP92] was proved by Givental and Lian-Liu-Yau [Giv96; LLY97] for complete intersections in projective space and by Coates-Corti-Lee-Tseng and Wang [CCLT09; Wan20] for complete intersections in weighted projective spaces.

• Bershadsky-Cecotti-Ooguri-Vafa [BCOV94] studied the B-model Kodaira-Spencer gravity and predicted that the generating series $F _ { g }$ of genus g Gromov-Witten invariants can be computed recursively using $F _ { h < g }$ by a Feynman rule up to a finite ambiguity. Mathematically, this corresponds to a sum over stable graphs, which index combinatorial strata of the moduli space ${ \overline { { \mathcal { M } } } } _ { g , n }$ of stable curves.

• Yamaguchi-Yau [YY04] studied the B-model theory further and predicted that a normalized generating series $P _ { g }$ of genus g Gromov-Witten invariants is a polynomial in five explicit generators for $Z _ { 5 } \subset \mathbb { P } ^ { 4 } , Z _ { 6 } \subset \mathbb { P } ( 1 ^ { 4 } , 2 ) , Z _ { 8 } \subset$ $\mathbb { P } ( 1 ^ { 4 } , 4 )$ , and $Z _ { 1 0 } \subset \mathbb { P } ( 1 ^ { 3 } , 2 , 5 )$ . They also predicted that these polynomials satisfy diferential equations in the generators, which we will refer to as Anomaly Equations.<sup>1</sup> These predictions were extended to the other examples by Huang-Klemm-Quackenbush [HKQ09].

• In mathematics, exact formulae for the genus 1 invariants were proved for complete intersections in projective spaces by Zinger and Popa [Zin09; Pop13] and for hypersurfaces in weighted projective spaces by the author [Lei24a].

• An exact formula for the genus 2 invariants of the quintic was proved by Guo-Janda-Ruan [GJR17] pending the proof of foundational results in logarithmic geometry. This was followed by a proof [GJR18] of the Anomaly Equations and finite generation conjecture, as well as some other results, for the quintic threefold.

• The Feynman rule, Anomaly Equations, and finite generation conjecture were proved independently by Chang-Guo-Li [CGL21; CGL19] using the theory of Mixed-Spin-P (MSP) fields developed in [CLLL19; CLLL22; CL20; CGLL21].<sup>2</sup> Using a slight generalization of their approach, the author proved the finite generation conjecture [Lei24a] for hypersurfaces in weighted projective space.

1.2. Setup and past work. Let $\mathbf { a } = ( 1 , 1 , 1 , 1 , 2 ) , ( 1 , 1 , 1 , 1 , 4 )$ , or (1, 1, 1, 2, 5), $\textstyle k : = \sum _ { i = 1 } ^ { 5 } a _ { i }$ , and set $p _ { k } : = { \frac { k } { a _ { 1 } \cdots a _ { 5 } } }$ . The I-function of $Z = Z _ { k } \subset \mathbb { P } ( \mathbf { a } )$ is given by

$$
\begin{array} { l } { { I ( q , z ) : = z \displaystyle \sum _ { d \geq 0 } q ^ { d } \frac { \prod _ { m = 1 } ^ { k d } ( k H + m z ) } { \prod _ { i = 1 } ^ { 5 } \prod _ { m = 1 } ^ { a _ { i } d } ( a _ { i } H + m z ) } } } \\ { { \mathrm { } = : I _ { 0 } ( q ) z + I _ { 1 } ( q ) H + I _ { 2 } ( q ) \displaystyle \frac { H ^ { 2 } } { z } + I _ { 3 } ( q ) \displaystyle \frac { H ^ { 3 } } { z ^ { 2 } } , } } \end{array}
$$

where $H = c _ { 1 } ( { \mathcal { O } } _ { \mathbb { P } ( \mathbf { a } ) } ( 1 ) )$ . If we set $\begin{array} { r } { r : = \frac { k ^ { k } } { a _ { 1 } ^ { a _ { 1 } } \cdots a _ { 5 } ^ { a _ { 5 } } } } \end{array}$ , then $I ( q , z )$ has radius of convergence $\textstyle { \frac { 1 } { r } }$

Remark 1.1. In [Giv96] and other work, the I-function difers from ours by a prefactor of $q ^ { \frac { H } { z } }$ . In particular, applying $z q { \frac { \mathrm { d } } { \mathrm { d } q } }$ to the usual conventions corresponds to applying $\textstyle H + z q { \frac { \mathrm { d } } { \mathrm { d } z } }$ to our I-function.

Our choice is natural from the perspective of quasimap theory. There, our Ifunction is obtained by localization on the stacky loop space [CCK15, Proposition 4.9] and appears in the wall-crossing formula of [Zho22].

Define $D : = q { \frac { \mathrm { d } } { \mathrm { d } q } }$ and define

$$
I _ { 1 1 } : = 1 + D \bigg ( \frac { I _ { 1 } ( q ) } { I _ { 0 } ( q ) } \bigg ) .
$$

Yamaguchi-Yau [YY04] defined infinitely many generators

$$
A _ { m } : = \frac { D ^ { m } I _ { 1 1 } } { I _ { 1 1 } } , \qquad B _ { m } : = \frac { D ^ { m } I _ { 0 } } { I _ { 0 } } , \qquad Y : = \frac { 1 } { 1 - r q } , \qquad \mathrm { a n d } \qquad X : = 1 - Y .
$$

For simplicity, denote $A : = A _ { 1 }$ and $B : = B _ { 1 }$

Remark 1.2. Our generators difer from the generators in [YY04; HKQ09] slightly. The variables difer by $\psi ^ { \mathsf { H K Q } } = ( r q ) ^ { - 1 }$ , and the generators in [HKQ09] are defined by

$$
A _ { m } ^ { \mathsf { H K Q } } : = \frac { \left( \psi ^ { \mathsf { H K Q } } \frac { \mathsf { d } } { \mathsf { d } \psi ^ { \mathsf { H K Q } } } \right) ^ { m } ( q I _ { 1 1 } ) } { q I _ { 1 1 } } \qquad \mathrm { a n d } \qquad B _ { m } ^ { \mathsf { H K Q } } : = \frac { \left( \psi ^ { \mathsf { H K Q } } \frac { \mathsf { d } } { \mathsf { d } \psi ^ { \mathsf { H K Q } } } \right) ^ { m } I _ { 0 } } { I _ { 0 } } .
$$

In particular, we have the relations

$$
A _ { m } = ( - 1 ) ^ { m } \left( \sum _ { j = 0 } ^ { m } \binom { m } { j } A _ { j } ^ { \sf H K Q } \right) \qquad \mathrm { a n d } \qquad B _ { m } = ( - 1 ) ^ { m } B _ { m } ^ { \sf H K Q } .
$$

Lemma 1.3 $\mathrm { ( [ Y Y 0 4 ] ) }$ . The ring $\mathscr { R } : = \mathbb { Q } [ A , B , B _ { 2 } , B _ { 3 } , Y ]$ contains all $A _ { m }$ and $B _ { m }$ for $m \geq 0$ . In particular, we have the relations

$$
A _ { 2 } = 2 B ^ { 2 } - 2 A B - 4 B _ { 2 } - X ( A + 2 B + r _ { 0 } ) ;
$$

$$
B _ { 4 } = - X ( 2 B _ { 3 } + ( 1 + r _ { 0 } ) B _ { 2 } + r _ { 0 } B + r _ { 1 } ) ,
$$

where $r _ { 0 }$ and $r _ { 1 }$ are given in Table 1.

Table 1. Values of $r _ { 0 } , r _ { 1 } , a _ { 0 , k } ,$ and $_ { a _ { 1 , k } }$ for diferent k
<table><tr><td> $k$ </td><td> $r _ { 0 }$ </td><td> $r _ { 1 }$ </td><td> $a _ { 0 , k }$ </td><td> $_ { a _ { 1 , k } }$ </td></tr><tr><td rowspan="2">6</td><td>13</td><td>5</td><td></td><td>7-4</td></tr><tr><td>36</td><td>162</td><td>12</td><td>7</td></tr><tr><td rowspan="2">8</td><td>11</td><td>105</td><td>13</td><td>11</td></tr><tr><td>32</td><td>4096</td><td></td><td>6</td></tr><tr><td rowspan="2">10</td><td>3</td><td>189</td><td>1-6</td><td>17</td></tr><tr><td>10</td><td>10000</td><td></td><td>12</td></tr></table>

We now define the generating function

$$
F _ { g } ( Q ) : = \delta _ { g , 0 } a _ { 0 , k } ( \log Q ) ^ { 3 } + \delta _ { g , 1 } a _ { 1 , k } \log Q + \sum _ { d } N _ { g , d } Q ^ { d } ,
$$

where the values of $\begin{array} { r } { a _ { 0 , k } = \frac { 1 } { 6 } \int _ { Z } H ^ { 3 } } \end{array}$ and $\begin{array} { r } { a _ { 1 , k } = - \frac { 1 } { 2 4 } \int _ { Z } c _ { 2 } ( Z ) \cup H } \end{array}$ are given in Table 1. This is not quite so well-behaved, so we will normalize it by defining

$$
P _ { g , m } : = { \frac { ( p _ { k } Y ) ^ { g - 1 } I _ { 1 1 } ^ { n } } { I _ { 0 } ^ { 2 g - 2 } } } { \left( Q { \frac { \mathrm { d } } { \mathrm { d } Q } } \right) } ^ { m } F _ { g } ( Q ) \Biggl | _ { Q = q e ^ { \frac { I _ { 1 } } { I _ { 0 } } } }
$$

for any $( g , m )$ satisfying $2 g - 2 + m > 0$ . These satisfy the recursive relation

$$
P _ { g , m + 1 } = ( D + ( g - 1 ) ( 2 B + X ) - m A ) P _ { g , m }
$$

and therefore can be computed from $P _ { 0 , 3 } = 1 , P _ { 1 , 1 }$ , and $P _ { g \geq 2 }$ . The main result of our previous work [Lei24a] is the following:

## Theorem 1.4. For any (g, m) satisfying $2 g - 2 + m > 0 , P _ { g , m } \in \mathcal { R } .$

We also proved the following exact formula for the genus 1 invariants of $Z { : }$

Theorem 1.5. We have

$$
P _ { 1 , 1 } = - \frac { 1 } { 2 } A + \bigg ( \frac { \chi ( Z ) } { 2 4 } - 2 \bigg ) B - \frac { 1 } { 1 2 } X + a _ { 1 , k } .
$$

For clarity, note that $\chi ( Z _ { 6 } ) = - 2 0 4 , \chi ( Z _ { 8 } ) = - 2 9 6 ,$ , and $\chi ( Z _ { 1 0 } ) = - 2 8 8$

## 1.3. Feynman rule.

Definition 1.6. Define the physicists’ propogators by the formulae

$$
\begin{array} { r } { E _ { \psi } : = B _ { 1 } , } \end{array}
$$

$$
E _ { \varphi \varphi } : = A _ { 1 } + 2 B _ { 1 } ,
$$

$$
E _ { \varphi \psi } : = - B _ { 2 } ,
$$

$$
\begin{array} { r } { E _ { \psi \psi } : = - B _ { 3 } + ( B _ { 1 } - X ) B _ { 2 } - r _ { 0 } B _ { 1 } X . } \end{array}
$$

For a choice of “gauge ${ \mathfrak { P } } \mathbb { G } : = ( c _ { 1 1 } , c _ { 1 2 } , c _ { 2 } , c _ { 3 } )$ , where $c _ { 1 1 } , c _ { 1 2 } \in \mathbb { Q } [ X ] _ { 1 } , c _ { 2 } \in \mathbb { Q } [ X ] _ { 2 }$ and $c _ { 3 } \in \mathbb { Q } [ X ] _ { 3 }$ , define

$$
\begin{array} { r l } & { \quad E _ { \psi } ^ { \mathbb { G } } : = E _ { \psi } + c _ { 1 1 } , } \\ & { \quad E _ { \varphi \varphi } ^ { \mathbb { G } } : = E _ { \varphi \varphi } + c _ { 1 2 } , } \\ & { \quad E _ { \varphi \psi } ^ { \mathbb { G } } : = E _ { \varphi \psi } - c _ { 1 2 } B _ { 1 } + c _ { 2 } , } \\ & { \quad E _ { \psi \psi } ^ { \mathbb { G } } : = E _ { \psi \psi } + c _ { 1 2 } B _ { 1 } ^ { 2 } - 2 c _ { 2 } B _ { 1 } + c _ { 3 } . } \end{array}
$$

Define $\begin{array} { r } { I _ { 2 2 } : = 1 + D \bigg ( \frac { D \big ( \frac { I _ { 2 } } { I _ { 0 } } \big ) + \frac { I _ { 0 } } { I _ { 0 } } } { I _ { 1 1 } } \bigg ) } \end{array}$ and $I _ { 3 3 } : = I _ { 1 1 }$ . Let $\varphi _ { i } = I _ { 0 } \cdot \cdot \cdot I _ { i i } H ^ { i }$ for $i = { 0 , 1 , 2 , 3 }$ and let ψ denote the ancestor class on ${ \overline { { \mathcal { M } } } } _ { g , n }$

Definition 1.7. Define the B-model Gromov-Witten correlators $P _ { g , m , n }$ by

$$
P _ { g , m , n } : = \left\{ { \begin{array} { l l } { ( 2 g + m + n - 3 ) _ { n } P _ { g , m } } & { 2 g - 2 + m > 0 } \\ { ( n - 1 ) ! { \Big ( } { \frac { \chi ( Z ) } { 2 4 } } - 1 { \Big ) } } & { ( g , m ) = ( 1 , 0 ) . } \end{array} } \right.
$$

Here, $( 2 g + m + n - 3 ) _ { r }$ is the falling Pochhammer symbol.

Note that these agree with the GW invariants

$$
\frac { ( p _ { k } Y ) ^ { m - 1 } } { I _ { 0 } ^ { 2 g - 2 + m + n } } \langle \varphi _ { 1 } ^ { \otimes m } , ( \varphi _ { 0 } \psi ) ^ { \otimes n } \rangle _ { g , m + n } ^ { Z }
$$

whenever $( g , m ) \neq ( 1 , 0 )$ , in which case the GW invariants is $( n - 1 ) ! \frac { \chi ( Z ) } { 2 4 }$ . Later, we will discover the meaning of this term.

Definition 1.8. Let $G _ { g , \ell }$ be the set of all stable graphs of genus g and ℓ legs and define

$$
f _ { g , m , n } ^ { \mathbf { B } , \mathbb { G } } : = \sum _ { \Gamma \in G _ { g , m + n } } { \frac { \mathrm { C o n t } _ { \Gamma } ^ { \mathbf { B } , \mathbb { G } } } { | \mathrm { A u t } \Gamma | } } ,
$$

where the contribution of a stable graph is defined by the following construction:

• At each leg, we place $\varphi _ { 1 } - E _ { \psi } ^ { \mathbb { G } } \varphi _ { 0 } \psi$ or φ<sub>0</sub>ψ;

• At each edge, we place the bivector

$$
V _ { \mathbf { B } , \mathbb { G } } : = E _ { \varphi \varphi } ^ { \mathbb { G } } \varphi _ { 1 } \otimes \varphi _ { 1 } + E _ { \varphi \psi } ^ { \mathbb { G } } ( \varphi _ { 1 } \otimes \varphi _ { 0 } \psi + \varphi _ { 0 } \psi \otimes \varphi _ { 1 } ) + E _ { \psi \psi } ^ { \mathbb { G } } \varphi _ { 0 } \psi \otimes \varphi _ { 0 } \psi ;
$$

• At each vertex, we place the linear map

$$
\varphi _ { 1 } ^ { \otimes m } \otimes ( \varphi _ { 0 } \psi ) ^ { \otimes n } \mapsto P _ { g , m , n } .
$$

The main result of this paper is the following polynomiality result for $f _ { g , m , n } ^ { \mathbf { B } }$

Theorem 1.9 (Corollary 4.9). For any $g , m , n$ and any choice of gauge G, we have

$$
f _ { g , m , n } ^ { \mathbf { B } , \mathbb { G } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + m } .
$$

If we specialize to $m = n = 0$ , then $G _ { g , 0 }$ contains a leading graph $\Gamma _ { 0 }$ with exactly one vertex (of genus g) and no edges. This graph contributes $P _ { g } ,$ while other graphs contribute linear combinations of products of $P _ { h < g , m , n }$ and the propogators. Therefore, if we know all $P _ { h < g , m , n } ,$ the formula

$$
P _ { g } = f _ { g } ^ { \mathbf { B } } - \sum _ { \Gamma \neq \Gamma _ { 0 } } { \frac { 1 } { | \mathrm { A u t } \Gamma | } } \mathrm { C o n t } _ { \Gamma } ^ { \mathbf { B } }
$$

implies that to compute $P _ { g } ,$ it sufices to compute $f _ { g } ^ { \mathbf { B } } \in \mathbb { Q } [ X ] _ { 3 g - 3 }$ . Because the degree 0 invariant

$$
N _ { g , 0 } = \frac { ( - 1 ) ^ { g } \chi ( Z ) \cdot | B _ { 2 g } | \cdot | B _ { 2 g - 2 } | } { 4 g \cdot ( 2 g - 2 ) \cdot ( 2 g - 2 ) ! }
$$

was already computed by Faber-Pandharipande [FP00], this allows us to fix the constant term of $f _ { g } ^ { \mathbf { B } }$ as $p _ { k } ^ { g - 1 } N _ { g , 0 }$ .

We will prove this result by reconstructing it from the A-model. We begin by constructing an A-model R-matrix, which will act on the Gromov-Witten potential of Z. It is engineered such that its edge contributions match the B-model edge contributions as much as possible.

Definition 1.10. In the basis $\varphi _ { 0 } , \ldots , \varphi _ { 3 }$ of $\mathcal { H } _ { Z }$ , define the A-model R-matrix by

$$
\begin{array} { r } { R ^ { \mathbf { A } , \mathbb { G } } ( z ) ^ { - 1 } : = I - \left( \begin{array} { c c c } { 0 } & { z E _ { \psi } ^ { \mathbb { G } } } & { z ^ { 2 } E _ { \varphi \psi } ^ { \mathbb { G } } } & { z ^ { 3 } E _ { 1 \psi ^ { 2 } } ^ { \mathbb { G } } } \\ { 0 } & { z E _ { \varphi \varphi } ^ { \mathbb { G } } } & { z ^ { 2 } E _ { 1 \varphi \psi } ^ { \mathbb { G } } } \\ & { 0 } & { z E _ { \psi } ^ { \mathbb { G } } } \\ & & { 0 } \end{array} \right) , } \end{array}
$$

where we define $E _ { 1 \varphi \psi } ^ { \mathbb { G } } : = - E _ { \psi } ^ { \mathbb { G } } E _ { \varphi \varphi } ^ { \mathbb { G } } - E _ { \varphi \psi } ^ { \mathbb { G } }$ and $\begin{array} { r } { E _ { 1 \psi ^ { 2 } } ^ { \mathbb { G } } : = - E _ { \psi } ^ { \mathbb { G } } E _ { \varphi \psi } ^ { \mathbb { G } } - E _ { \psi \psi } ^ { \mathbb { G } } . } \end{array}$

We will now define an A-model Feynman rule.

Definition 1.11. For $\mathbf { a } \in \{ 0 , 1 , 2 , 3 \} ^ { n }$ and $ { \mathbf { b } } \in \mathbb { Z } _ { \geq 0 } ^ { n }$ , define

$$
f _ { g , m , n } ^ { \mathbf { A } , \mathbb { G } } : = \sum _ { \Gamma \in G _ { g , m + n } } { \frac { \operatorname { C o n t } _ { \Gamma } ^ { \mathbf { A } , \mathbb { G } } } { | \mathrm { A u t } \Gamma | } } ,
$$

where the contribution of a stable graph is defined by the following construction:

• At each leg, we place $R ^ { \mathbf { A } , \mathbb { G } } ( z ) ^ { - 1 } \varphi _ { a } \psi ^ { b } ;$

• At each edge, we place the bivector

$$
\begin{array} { r l } & { { \displaystyle V _ { { \bf A } , \mathbb { G } } : = \sum _ { i = 0 } ^ { 3 } \frac { \varphi _ { i } \otimes \varphi _ { 3 - i } - R ^ { { \bf A } } ( \psi ) ^ { - 1 } \varphi _ { i } \otimes R ^ { { \bf A } } ( \psi ^ { \prime } ) ^ { - 1 } \varphi _ { 3 - i } } { \psi + \psi ^ { \prime } } } } \\ & { \quad \quad \quad = E _ { \varphi \varphi } \varphi _ { 1 } \otimes \varphi _ { 1 } + E _ { \varphi \psi } ( \varphi _ { 1 } \otimes \varphi _ { 0 } \psi ^ { \prime } + \varphi _ { 0 } \psi \otimes \varphi _ { 1 } ) + E _ { \psi \psi } ( \varphi _ { 0 } \psi \otimes \varphi _ { 0 } \psi ^ { \prime } ) } \\ & { \quad \quad \quad \quad + E _ { \psi } ( \varphi _ { 0 } \otimes \varphi _ { 2 } + \varphi _ { 2 } \otimes \varphi _ { 0 } ) + E _ { 1 \varphi \psi } ( \varphi _ { 0 } \otimes \varphi _ { 1 } \psi ^ { \prime } + \varphi _ { 1 } \psi \otimes \varphi _ { 0 } ) } \\ & { \quad \quad \quad \quad + E _ { 1 \psi ^ { 2 } } ( \varphi _ { 0 } \otimes \varphi _ { 0 } ( \psi ^ { \prime } ) ^ { 2 } + \varphi _ { 0 } \psi ^ { 2 } \otimes \varphi _ { 0 } ) . } \end{array}
$$

• At each vertex, we place the linear map

$$
{ \frac { ( p _ { k } Y ) ^ { g - 1 } } { I _ { 0 } ^ { 2 g - 2 + n } } } \langle - \rangle _ { g , n } ^ { Z } .
$$

Using the theory of MSP fields, we will prove a polynomiality result for $f _ { g , { \bf a } , { \bf b } } ^ { { \bf A } , \mathbb { G } } .$ Along the way, we discover that the MSP R-matrix defined in [Lei24a] (see (2.1)) factors as the product of a matrix $R ^ { X }$ which satisfies an X-polynomiality property and $R ^ { \mathbf { A } , \mathbb { G } }$ and obtain a similar degree bound for the level 0 part of the full MSP theory.

Theorem 1.12 (Corollary 3.12). For any choice of gauge G and any g, n such that $2 g - 2 + n > 0 _ { ; }$ , we have

$$
f _ { g , \mathbf { a } , \mathbf { b } } ^ { \mathbf { A } , \mathbb { G } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + n - \sum b _ { i } } .
$$

In particular, when we set $\mathbf { a } = \left( 1 ^ { m } , 0 ^ { n } \right)$ and $\mathbf { b } = ( 0 ^ { m } , 1 ^ { n } )$ , we define

$$
f _ { g , m , n } ^ { \mathbf { A } , G } : = f _ { g , ( 1 ^ { m } , 0 ^ { n } ) , ( 0 ^ { m } , 1 ^ { n } ) } ^ { \mathbf { A } , \mathbb { G } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + m } .
$$

Note that the A-model Feynman rule has three extra edge contributions, which contain four extra variables compared to the B-model Feynman rule. Remarkably, the contributions of the correction term in $g = 1$ , the extra A-model edge contributions, and the four extra A-model variables cancel out to yield the following result.

Theorem 1.13 (Theorem 4.8). The A-model and B-model graph sums satisfy the relation

$$
f _ { g , m , n } ^ { \mathbf { A } , \mathbb { G } } = f _ { g , m , n } ^ { \mathbf { B } , \mathbb { G } } + \delta _ { g , 1 } \delta _ { m , 0 } ( n - 1 ) ! .
$$

## 1.4. Anomaly equations. In Section 5, we prove the following anomaly equations:

Theorem 1.14 (Theorem 5.1). The $P _ { g , m }$ satisfy the diferential equations

$$
- \partial _ { A } P _ { g } = \frac { 1 } { 2 } \Biggl ( P _ { g - 1 , 2 } + \sum _ { g _ { 1 } + g _ { 2 } = g } P _ { g _ { 1 } , 1 } P _ { g _ { 2 } , 2 } \Biggr ) ,
$$

$$
( - 2 \partial _ { A } + \partial _ { B } + ( A + 2 B ) \partial _ { B _ { 2 } } - ( ( B - X ) ( A + 2 B ) - B _ { 2 } - r _ { 0 } X ) \partial _ { B _ { 3 } } ) P _ { g } = 0 .
$$

The first equation is proved directly by diferentiating the B-model Feynman rule, while the second is equivalent to a mysterious reduction of generators (Theorem 5.6) found by Yamaguchi-Yau [YY04]. In particular, they consider particular $v _ { 1 } , v _ { 2 } , v _ { 3 } \in$ R and conjecture that for all $g \ge 2 , P _ { g } \in \mathbb { Q } [ v _ { 1 } , v _ { 2 } , v _ { 3 } , X ]$

## 1.5. Outline. The paper is organized as follows:

• In §2, we review the construction of the MSP [0, 1] theory, construct the MSP [0] and [1] theories, and prove polynomiality of the MSP [1] theory.

• In §3, we prove the polynomiality of the MSP [0] theory and the A-model graph sum using a bootstrapping argument when $\mathbb { G } = ( 0 , 0 , 0 , 0 )$ The A-model Feynman rule for a general gauge (Theorem 1.12) follows as a corollary.

• In §4, we rewrite both the A-model Feynman rule and B-model Feynman rule using the formalism of geometric quantization of symplectic linear transformations. We then study the efect of the extra contributions in the A-model and prove Theorem 1.13 by direct computation. The B-model Feynman rule (Theorem 1.9) follows as a corollary.

• In §5, we prove Theorem 1.14.

## 1.6. Conventions. We will use the following conventions in this paper:

• We will ignore the odd cohomology of our target Z. All operators in this paper will preserve the $\mathbb { Z } / 2$ grading on cohomology and are the identity on odd classes.

• The theory of MSP fields depends on a positive integer N. We will assume that N is an odd prime. Whenever we $\operatorname { f i x } g , n$ , we will always assume that $N \gg 3 g - 3 + n .$

• We will consider $\mathbf { T } = ( \mathbb { C } ^ { \times } ) ^ { N }$ -equivariant invariants. Our convention is that after equivariant integration, we will specialize our equivariant parameters by $t _ { \alpha } = - \zeta _ { N } ^ { \alpha } t$ . At various points in the paper, we will specialize $t ^ { N } = - 1$

• Whenever we compute using equivariant integration, we will make the substitution $\begin{array} { r } { q ^ { \prime } = \frac { - q } { t ^ { N } } } \end{array}$ . Note the specialization $t ^ { \check { N } } = - 1$ makes $q ^ { \prime } = q$

Acknowledgements. The author is grateful to Chiu-Chu Melissa Liu for all of her helpful advice and for proposing this project. The author would like to thank Konstantin Aleshkin and Shuai Guo for helpful discussions, and Dimitri Zvonkine for his lectures about CohFTs and R-matrix actions at the Simons Center for Geometry and Physics in August 2023. The author would also like to thank Shuai Guo for his hospitality during the author’s visit to Peking University in July 2024, when part of this work was completed. Finally, the author would like to thank Felix Janda and Yongbin Ruan for expressing interest in the results of this paper and its prequel [Lei24a].

## 2. MSP [0] and [1] theories

In this section, we will define the MSP [0] theory and [1] theory and prove a polynomiality property for the [1] theory. We will refer the reader to [PPZ15] and [CGL19, §2, Appendix C] for a discussion of CohFTs and R-matrix actions, including in the cases when $R _ { 0 } \neq I$ and when source and target of the R-matrix are diferent vector spaces or have diferent pairings.

2.1. The MSP [0, 1] theory. Let N be a positive integer. First, the stack ${ \mathcal { W } } _ { g , n , ( d , 0 ) }$ was constructed in [Lei24b] and MSP invariants were constructed in [Lei24a] for the state space

$$
\mathcal { H } : = H ^ { \ast } ( Z ) \oplus \bigoplus _ { \alpha = 1 } ^ { N } H ^ { \ast } ( \mathrm { p t } _ { \alpha } ) = : \mathcal { H } _ { Z } \oplus \bigoplus _ { \alpha } \mathcal { H } _ { \alpha } = : \mathcal { H } _ { Z } \oplus \mathcal { H } _ { 1 } .
$$

The pairing is given by

$$
\begin{array} { r l } & { ( x , y ) : = \displaystyle \int _ { Z } \frac { x y } { - t ^ { N } } + \sum _ { \alpha } \frac { - p _ { k } } { N t _ { \alpha } ^ { 3 } t ^ { N } } x y \bigg \vert _ { \mathrm { p t } _ { \alpha } } } \\ & { \qquad = : ( x | _ { Z } , y | _ { Z } ) ^ { Z , \mathrm { t w } } + \sum _ { \alpha } ( x | _ { \mathrm { p t } _ { \alpha } } , y | _ { \mathrm { p t } _ { \alpha } } ) ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } } . } \end{array}
$$

We will now give several bases which we will consider in the rest of the paper.

(1) We consider $Z \sqcup \sqcup _ { \alpha = 1 } ^ { N } { \mathrm { p t } } _ { \alpha } = ( x _ { 1 } ^ { k / a _ { 1 } } + \cdot \cdot \cdot + x _ { 5 } ^ { k / a _ { 5 } } = 0 ) ^ { \mathbf { T } } \subset \mathbb { P } ( \mathbf { a } , 1 ^ { N } )$ and let $p = c _ { 1 } ( \mathcal { O } _ { \mathbb { P } ( \mathbf { a } , 1 ^ { N } ) } ( 1 ) )$ . Then define $\phi _ { j } : = p ^ { j } \mathrm { f o r } j = 1 , . . . N + 3 ;$

(2) Note that there is the natural basis $\{ 1 , H , H ^ { 2 } , H ^ { 3 } \}$ of $\mathcal { H } _ { Z }$ and $\lbrace { \mathbf { 1 } } _ { \alpha } \rbrace _ { \alpha = 1 } ^ { N }$ of $\begin{array} { r } { \mathcal { H } _ { 1 } : = \bigoplus _ { \alpha } \mathcal { H } _ { \alpha } ; } \end{array}$

(3) We may normalize the previous basis<sup>3</sup> and consider $\varphi _ { b } = I _ { 0 } I _ { 1 1 } \cdot \cdot \cdot I _ { b b } H ^ { b }$ where $\begin{array} { r } { I _ { 2 2 } = 1 + D \bigg ( \frac { D \big ( \frac { I _ { 2 } } { I _ { 0 } } \big ) + \frac { I _ { 1 } } { I _ { 0 } } } { I _ { 1 1 } } \bigg ) } \end{array}$ and $I _ { 3 3 } = I _ { 1 1 }$ . We will also consider $\bar { \mathbf { 1 } } _ { \alpha } = L ^ { - \frac { N + 3 } { 2 } } \mathbf { 1 } _ { \alpha } .$

Before we continue, we will define several CohFTs related to C using the MSP virtual localization formula [Lei24b, §6]. First, for any smooth projective variety $Z ,$ the Gromov-Witten CohFT associated to Z is given by

$$
\Omega _ { g , n } ^ { Z } ( \tau _ { 1 } , \dots , \tau _ { n } ) : = \sum _ { d \in H _ { 2 } ( Z , \mathbb { Z } ) } q ^ { d } \operatorname { s t } _ { * } ^ { Z } \left( \prod _ { i = 1 } ^ { n } \operatorname { e v } _ { i } ^ { * } ( \tau _ { i } ) \cap [ \overline { { \mathbb { M } } } _ { g , n } ( Z , d ) ] ^ { \operatorname { v i r } } \right) ,
$$

where $\mathfrak { s t } ^ { Z } : \overline { { \mathcal { M } } } _ { g , n } ( Z , d ) \to \overline { { \mathcal { M } } } _ { g , n }$ is the stabilization morphism and $\tau _ { i } \in H ^ { * } ( Z )$ . In the MSP virtual localization formula, the contribution of a vertex at level 0 is given by

$$
\begin{array} { r } { ( - t ^ { N } ) ^ { - ( d + 1 - g ) } [ \overline { { \mathcal { M } } } _ { g , n } ( Z , d ) ] ^ { \mathrm { v i r } } = : [ \overline { { \mathcal { M } } } _ { g , n } ( Z , d ) ] ^ { \mathrm { t w } } . } \end{array}
$$

Replacing $[ \overline { { \mathcal { M } } } _ { g , n } ( Z , d ) ] ^ { \mathrm { v i r } }$ by $[ \overline { { \mathcal { M } } } _ { g , n } ( Z , d ) ] ^ { \mathrm { t w } }$ in the formula for $\Omega ^ { Z }$ , we obtain the CohFT $\Omega ^ { Z , \mathrm { { , t w } } }$

We will need to consider a shift of the Gromov-Witten CohFT of Z by the mirror map $\begin{array} { r } { \tau _ { Z } ( q ) : = \frac { I _ { 1 } ( q ) } { I _ { 0 } ( q ) } H } \end{array}$ . This is given by the formula

$$
\begin{array} { l } { \Omega _ { g , n } ^ { Z , \tau _ { Z } ( q ) } ( - ) : = \displaystyle \sum _ { d , m } \frac { q ^ { d } } { m ! } \Omega _ { g , n + m } ^ { Z } ( - , \tau _ { Z } ( q ) ^ { m } ) } \\ { = \displaystyle \sum _ { d } Q ( q ) ^ { d } \Omega _ { g , n + m } ^ { Z } ( - ) , } \end{array}
$$

where $\begin{array} { r } { Q ( q ) : = q e ^ { \frac { I _ { 1 } ( q ) } { I _ { 0 } ( q ) } } } \end{array}$ is the mirror map.

For each of the isolated points $\mathrm { p t } _ { \alpha }$ , we may consider the vertex contribution

$$
\begin{array} { r l } & { [ \overline { { \mathbb { M } } } _ { g , n } ] ^ { \alpha , \mathrm { t w } } } \\ & { : = ( - 1 ) ^ { 1 - g } \frac { p _ { k } t _ { \alpha } \cdot \prod _ { i = 1 } ^ { 5 } e _ { \mathbf { T } } \left( \mathbb { E } _ { g , n } ^ { \vee } \cdot \left( - a _ { i } t _ { \alpha } \right) \right) \cdot \prod _ { \beta \neq \alpha } e _ { \mathbf { T } } \left( \mathbb { E } _ { g , n } ^ { \vee } \cdot \left( t _ { \beta } - t _ { \alpha } \right) \right) } { \left( - t _ { \alpha } \right) ^ { 5 } \cdot e _ { \mathbf { T } } \left( \mathbb { E } _ { g , n } \cdot k t _ { \alpha } \right) \cdot \prod _ { \beta \neq \alpha } \left( t _ { \beta } - t _ { \alpha } \right) } \cap [ \overline { { \mathbb { M } } } _ { g , n } ] . } \end{array}
$$

These classes define a CohFT $\Omega ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } }$ , and restricting to the topological part

$$
[ \overline { { \mathscr { M } } } _ { g , n } ] ^ { \mathrm { t o p } } = \bigg ( \frac { 1 } { p _ { k } } N ( - t _ { \alpha } ) ^ { N + 3 } \bigg ) ^ { g - 1 } [ \overline { { \mathscr { M } } } _ { g , n } ]
$$

gives the topological part $\omega ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } }$ of the CohFT.

In [Lei24a, §2.1], we defined MSP invariants $\left. - \right. _ { g , n } ^ { M }$ using virtual localization, whose explicit formula was proved in [Lei24b, §5]. Recall that for any cohomological field theory, Givental’s theory [Giv04] considers the fundamental solution of the quantum diferential equation (or Dubrovin connection), which is given by

$$
S _ { \tau } ^ { M } ( z ) x = x + \sum _ { a , n } \frac { 1 } { n ! } e ^ { a } \biggl \langle \frac { x } { z - \psi } , e _ { a } , \tau ^ { n } \biggr \rangle _ { 0 , n + 2 } ^ { M } .
$$

Here, $\{ e _ { a } \}$ is a basis of H and $\{ e ^ { a } \}$ is its dual basis. We will now restrict to the case $\tau = 0$ and abbreviate the fundamental solution to $S ^ { M } ( z )$ . We also considered the corresponding fundamental solutions $S ^ { Z } : = S _ { \tau _ { Z } ( q ) } ^ { Z }$ where $\begin{array} { r } { \tau _ { Z } = \frac { I _ { 1 } ( q ) } { I _ { 0 } ( q ) } H } \end{array}$ and $S ^ { \mathrm { p t } _ { \alpha } } : = S _ { \tau _ { \alpha } } ^ { \mathrm { p t } _ { \alpha } }$ , where $\begin{array} { r } { \tau _ { \alpha } = - t _ { \alpha } \int _ { 0 } ^ { q } ( L ( x ) - 1 ) \frac { \mathrm { d } x } { x } } \end{array}$ , where $L = ( 1 + r x ) ^ { \frac { 1 } { N } }$

Finally, we defined the MSP R-matrix by the formula

$$
S ^ { M } ( z ) ( ^ { \mathrm { d i a g } \{ \Delta ^ { \mathrm { p t } _ { \alpha } } ( z ) \} _ { \alpha = 1 } ^ { N } }   _ { 1 } ) =  R ( z ) ( ^ { \mathrm { d i a g } \{ S ^ { \mathrm { p t } _ { \alpha } } ( z ) \} _ { \alpha = 1 } ^ { N } }   _ {  S ^ { Z } ( z ) ) }  _ { q  q ^ { \prime } } ,\tag{2.1}
$$

where $\Delta ^ { \mathrm { p t } _ { \alpha } } ( z )$ is the Quantum Riemann-Roch [CG07] operator given by the formula

$$
\begin{array} { r l } & { \Delta ^ { \mathrm { p t } _ { \alpha } } ( z ) : = \exp \Bigg [ \displaystyle \sum _ { m \geq 0 } \frac { B _ { 2 m } } { 2 m ( 2 m - 1 ) } \bigg ( \displaystyle \sum _ { i = 1 } ^ { 5 } \frac { 1 } { ( - a _ { i } t _ { \alpha } ) ^ { 2 m - 1 } } } \\ & { \qquad + \left. \frac { 1 } { ( k t _ { \alpha } ) ^ { 2 m - 1 } } + \displaystyle \sum _ { \beta \neq \alpha } \frac { 1 } { ( t _ { \beta } - t _ { \alpha } ) ^ { 2 m - 1 } } \right) z ^ { 2 m - 1 } \Bigg ] . } \end{array}
$$

Here, the $B _ { 2 k }$ are the Bernoulli numbers.

In $[ \mathrm { L e i 2 4 a } , \ \ S 5 ]$ , we explained how to use the explicit formula for the quantum diferential equation given in $\mathrm { [ L e i 2 4 a , }$ , Lemma 2.18] to compute the entries of $R ( z ) ^ { * }$ when the input basis is $\{ 1 , \stackrel { \cdot } { p } , \dotsc , p ^ { N + 3 } \}$ and the output basis is $\{ \varphi _ { 0 } , \ldots , \varphi _ { 3 } \} \cup$ $\{ \bar { \bf 1 } _ { \alpha } \} _ { \alpha = 1 } ^ { N }$ . In particular, the entries are elements of R up to some normalization.

Definition 2.1 ([Lei24a, Theorem 3.6]). Define the local theory by the formula

$$
\Omega ^ { \mathrm { l o c } } : = \Omega ^ { Z , \mathrm { t w } } \oplus \bigoplus _ { \alpha = 1 } ^ { N } \omega ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } }
$$

and the MSP [0, 1] theory by the formula

$$
\Omega ^ { [ 0 , 1 ] } : = R . \Omega ^ { \mathrm { l o c } } .
$$

Remark 2.2. Note that the [0, 1] theory was originally defined using virtual localization. The fixed loci of $\mathcal { W } _ { g , n , ( d , 0 ) }$ are described using localization graphs Θ whose vertices can be partitioned as $V = V _ { 0 } \sqcup V _ { 1 } \sqcup V _ { \infty }$ . We then only consider those Θ for which $V _ { \infty } = \emptyset$ when defining the $[ 0 , 1 ]$ theory. In [Lei24a, §3], we proved that it is equivalent to the definition we give here. In addition, when N is very large relative to g, n, we obtain a simpler formula for the tail contributions at level 0.

Remark 2.3. In contrast to the usual setting (see [PPZ15] for example), our $R ( z ) =$ $R _ { 0 } + R _ { 1 } z + \cdots$ · does not satisfy $R _ { 0 } = \mathrm { I d }$ . However, we can relate this more general case of R-matrix actions to the usual setting via the dilaton flow, for example see [CGL19, Appendix C].

2.2. The MSP [0] and [1] theories. We will now define restricted versions of the MSP [0, 1] CohFTs, which we will call the [0] and [1] theories. First, recall that [CGL19, §2] gives a definition of the R-matrix action on CohFTs when the source and target of R are not the same vector space. In particular, we only need that $R ( - z ) ^ { * } R ( z ) = { \mathrm { I d } }$ , which in particular implies that $R _ { 0 }$ is injective.

Definition 2.4. Define the restricted R-matrices $R ^ { [ 0 ] } ( z )$ and $R ^ { [ 1 ] } ( z )$ by the formulae

$$
\begin{array} { r } { R ^ { [ 0 ] } ( z ) = R ( z ) \vert _ { \mathcal { H } _ { z } } , } \\ { R ^ { [ 1 ] } ( z ) = R ( z ) \vert _ { \mathcal { H } _ { 1 } } . } \end{array}
$$

Because the MSP R-matrix R(z) satisfies $R ( - z ) ^ { * } R ( z ) = \mathrm { I d } , R ^ { [ 0 ] } ( z )$ and $R ^ { [ 1 ] } ( z )$ satisfy the identities

$$
R ^ { [ 0 ] } ( - z ) ^ { \ast } R ^ { [ 0 ] } ( z ) = \mathrm { I d } _ { \mathcal { H } _ { z } } ,
$$

$$
R ^ { [ 1 ] } ( - z ) ^ { * } R ^ { [ 1 ] } ( z ) = \mathrm { I d } _ { \mathcal { H } _ { 1 } } ,
$$

$$
R ^ { [ 0 ] } ( - z ) ^ { \ast } R ^ { [ 1 ] } ( z ) = R ^ { [ 1 ] } ( - z ) ^ { \ast } R ^ { [ 0 ] } ( z ) = 0 .
$$

Definition 2.5. Define the MSP [0] theory by the formula

$$
\Omega ^ { [ 0 ] } : = R ^ { [ 0 ] } . \Omega ^ { Z , \mathrm { t w } }
$$

and the MSP [1] theory by the formula

$$
\Omega ^ { [ 1 ] } : = R ^ { [ 1 ] } . \bigoplus _ { \alpha = 1 } ^ { N } \omega ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } } .
$$

Our immediate goal is now to prove a polynomiality result for the MSP [0] theory. We will do this by studying the MSP [0, 1] theory and the [1] theory, which is similar to the argument used to prove the polynomiality of the [0, 1] theory [Lei24a, Theorem 4.1]. We will first describe a bipartite graph decomposition of the [0, 1] theory, then prove the polynomiality of the [1] theory. After some work, we will apply the polynomiality of the [1] theory and of the [0, 1] theory to deduce the polynomiality of the [0] theory.

Definition 2.6. Define $\mathcal { G } _ { g , n } ^ { [ 0 , 1 ] }$ to be the set of stable bipartite graphs of total genus g and n legs. These are stable graphs with a partition $V = V _ { 0 } \sqcup V _ { 1 }$ making the graph bipartite.

Theorem 2.7. There is a decomposition of the $M S P \left[ 0 , 1 \right]$ theory in terms of stable bipartite graphs as

$$
\begin{array} { r l } & { \Omega _ { g , n } ^ { [ 0 , 1 ] } ( \tau _ { 1 } , \dots , \tau _ { n } ) = \displaystyle \sum _ { \Lambda \in \mathcal { G } _ { g , n } ^ { [ 0 , 1 ] } } \bigotimes _ { v \in V _ { 0 } } \Omega _ { g _ { v } , n _ { v } } ^ { [ 0 ] } \otimes \bigotimes _ { v \in V _ { 1 } } \Omega _ { g _ { v } , n _ { v } } ^ { [ 1 ] } } \\ & { \qquad \quad \left( \displaystyle \bigotimes _ { v \in V _ { 0 } } \tau _ { \ell } \otimes \bigotimes _ { v \in V _ { \ell } } \tau _ { \ell } \otimes \bigotimes _ { e \in E } V ^ { 0 1 } ( \psi , \psi ^ { \prime } ) \right) , } \end{array}
$$

where we define

$$
V ^ { 0 1 } ( z , w ) : = \sum _ { \alpha = 1 } ^ { N } \frac { R ^ { [ 1 ] } ( z ) - R ^ { [ 1 ] } ( - w ) } { z + w } \mathbf { 1 } _ { \alpha } \otimes R ^ { [ 1 ] } ( w ) \mathbf { 1 } ^ { \alpha } .
$$

Proof. Recall that the edge contribution in the definition of the MSP [0, 1] theory is given by

$$
\begin{array} { r l } { \mathrm { C o n t } _ { E _ { 0 1 } } } & { = \displaystyle \sum _ { i = 1 } ^ { N + 3 } \frac { \phi _ { i } \otimes \phi ^ { i } - R ( z ) ^ { - 1 } \phi _ { i } \otimes R ( w ) ^ { - 1 } \phi ^ { i } } { z + w } \bigg | _ { \displaystyle \mathbb { X } _ { G \otimes \mathbb { S } \mathbb { R } _ { 1 } } } } \\ & { = - \displaystyle \sum _ { a = 1 } ^ { N } \frac { R ( - z ) ^ { \star } R ( - w ) { \mathbf 1 } _ { a } \otimes { \mathbf 1 } ^ { \alpha } } { z + w } \bigg | _ { \displaystyle \mathbb { X } _ { G \otimes \mathbb { S } \mathbb { R } _ { 1 } } } } \\ & { = - \displaystyle \sum _ { a = 1 } ^ { N } \frac { R ^ { [ 0 ] } ( - z ) ^ { \star } R ^ { [ 1 ] } ( - w ) { \mathbf 1 } _ { \alpha } \otimes { \mathbf 1 } ^ { \alpha } } { z + w } } \\ & { = \displaystyle \sum _ { a = 1 } ^ { N } \frac { R ^ { [ 0 ] } ( - z ) ^ { \star } ( R ^ { [ 1 ] } ( z ) - R ^ { [ 1 ] } ( - w ) ) { \mathbf 1 } _ { \alpha \otimes \mathbb { S } \mathbb { R } ^ { \alpha } } } { z + w } } \\ & { = ( R ^ { [ 0 ] } ( - z ) ^ { \star } \otimes R ^ { [ 1 ] } ( - w ) ^ { \star } V ^ { 0 } [ z , w ) ) . } \end{array}
$$

The result then follows from the definition of the R-matrix action as a sum over stable graphs. □

2.3. Polynomiality of the [1] theory. Recall that we defined the edge contributions to the [0, 1] theory by

$$
\begin{array} { l } { { \displaystyle V ( z , w ) = \sum _ { j = 0 } ^ { N + 3 } \frac { \phi _ { j } \otimes \phi ^ { j } - R ( z ) ^ { - 1 } \phi _ { j } \otimes R ( w ) ^ { - 1 } \phi ^ { j } } { z + w } } } \\ { { \displaystyle ~ = : \sum _ { m , n } V _ { m n } z ^ { m } w ^ { n } . } } \end{array}
$$

Lemma 2.8. Let $m , n \geq 0 , a = 0 , \ldots , N + 3$ , and $\alpha , \beta \in \{ 1 , \ldots , N \}$ . In $I L e i 2 4 a ,$ $\it { \ S 5 . 3 ] }$ , we defined

$$
( R _ { m } ) _ { a } ^ { \alpha } : = L _ { \alpha } ^ { - a - m } ( R _ { m } \bar { \bf 1 } ^ { \alpha } , \phi _ { a } ) .
$$

Then

(1) $( R _ { m } ) _ { a } ^ { \alpha }$ is independent of α and $( R _ { m } ) _ { a } ^ { \alpha } \in \mathbb { Q } [ X ] _ { m + \lfloor \frac { a } { N } \rfloor } ;$

(2) The V -bivector has the form

$$
V _ { m n } | _ { \mathcal { H } _ { 1 } \otimes \mathcal { H } _ { 1 } } = L ^ { - 3 } t ^ { N } \sum _ { \alpha , \beta } \sum _ { s } L _ { \alpha } ^ { s - m } L _ { \beta } ^ { 2 - s - n } ( V _ { m n } ) ^ { \alpha \beta ; s } \mathbf { 1 } _ { \alpha } \otimes \mathbf { 1 } _ { \beta } ,
$$

where $( V _ { m n } ) ^ { \alpha \beta ; s } \in \mathbb { Q } [ X ] _ { m + n + 1 }$ is independent of $\alpha , \beta .$

Proof. Note that (1) is [Lei24a, Lemma 5.9]. The proof of (2) is the same as [CGL21, Lemma C.1]. □

Definition 2.9. When ⋆ is either [0], [1], or [0, 1], define

$$
f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { \star } : = \int _ { \overline { { \mathcal { M } } } _ { g , n } } \prod _ { i = 1 } ^ { n } \psi _ { i } ^ { b _ { i } } \Omega _ { g , n } ^ { \star } ( \phi _ { a _ { 1 } } , \ldots , \phi _ { a _ { n } } )
$$

and the [1] theory with special insertions

$$
{ f _ { g , ( { \bf a } , { \bf b } ) ( { \bf a ^ { \prime } } , { \bf b } ^ { \prime } ) } ^ { [ 1 ] } } : = L ^ { \sum _ { i = 1 } ^ { m } a _ { i } ^ { \prime } } \int _ { \overline { { \mathcal { M } } } _ { g , n + m } } \prod _ { i = 1 } ^ { n } \psi _ { i } ^ { b _ { i } } \prod _ { j = 1 } ^ { m } \psi _ { n + j } ^ { b _ { j } ^ { \prime } } \qquad
$$

for $\mathbf { a } \in \{ 0 , \ldots , N + 3 \} ^ { n } , \mathbf { a } ^ { \prime } \in \{ 1 , \ldots , N \} ^ { m } , \mathbf { b } \in \mathbb { Z } _ { > 0 } ^ { n }$ , and $\mathbf { b } ^ { \prime } \in \mathbb { Z } _ { \geq 0 } ^ { m }$ . Here, we define $\begin{array} { r } { \bar { \phi } _ { a } : = L ^ { - \frac { N + 3 } { 2 } } L ^ { a } p ^ { a } | _ { \mathcal { H } _ { 1 } } = \sum _ { \alpha = 1 } ^ { N } L _ { \alpha } ^ { a } \bar { \bf 1 } _ { \alpha } . } \end{array}$

Definition 2.10. For a tuple $\mathbf { a } \in \mathbb { Z } _ { \geq 0 } ^ { n } .$ , define $\textstyle | \mathbf { a } | : = \sum _ { i = 1 } ^ { n } a _ { i }$ and $\begin{array} { r } { \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor : = \sum _ { i = 1 } ^ { n } \left\lfloor \frac { a _ { i } } { N } \right\rfloor } \end{array}$ Lemma 2.11. Let $N \gg 3 g - 3 + n + m$ . Define

$$
c : = \frac { | \mathbf { a } | + | \mathbf { a } ^ { \prime } | + | \mathbf { b } | + | \mathbf { b } ^ { \prime } | - n - m } { N } .
$$

If $c \in \mathbb { Z }$ , then

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { g - 1 + r } f _ { g , ( { \bf a } , { \bf b } ) , ( { \bf a } ^ { \prime } , { \bf b } ^ { \prime } ) } ^ { [ 1 ] }
$$

is a polynomial in X of degree at most $\begin{array} { r } { 3 g - 3 + n + m - | { \bf { b } } | - | { \bf { b } } ^ { \prime } | + \left\lfloor \frac { { \bf { a } } } { N } \right\rfloor } \end{array}$ . Otherwise, $f _ { g , ( { \bf a } , { \bf b } ) , ( { \bf a } ^ { \prime } , { \bf b } ^ { \prime } ) } ^ { [ 1 ] } = 0$

Proof. Recall that $f _ { g , ( { \mathbf a } , { \mathbf b } ) , ( { \mathbf a } ^ { \prime } , { \mathbf b } ^ { \prime } ) } ^ { [ 1 ] }$ is defined as a sum of stable graph contributions, where the contribution from any stable graph is computed as follows:

(1) At every leg with insertion $\phi _ { a } \psi ^ { b }$ , we place

$$
R ^ { [ 1 ] } ( - \psi ) ^ { * } \psi _ { a } \psi ^ { b } = \sum _ { \alpha , m } L _ { \alpha } ^ { a - m } ( - 1 ) ^ { m } \psi ^ { m + b } \bar { \mathbf { 1 } } _ { \alpha } = L ^ { - \frac { N + 3 } { 2 } } \sum _ { \alpha , m } L _ { \alpha } ^ { a - m } ( - 1 ) ^ { m } \psi ^ { m + b } \mathbf { 1 } _ { \alpha } ;
$$

(2) At every leg with special insertion $R ( \psi ^ { \prime } ) \bar { \phi } _ { a ^ { \prime } } \psi ^ { b ^ { \prime } }$ , we place

$$
R ^ { [ 1 ] } ( - \psi ) ^ { * } R ( \psi ) \bar { \phi } _ { a ^ { \prime } } \psi ^ { b ^ { \prime } } = \sum _ { \alpha } L _ { \alpha } ^ { a ^ { \prime } } \bar { \bf 1 } _ { \alpha } \psi ^ { b ^ { \prime } } = L ^ { - \frac { N + 3 } { 2 } } \sum _ { \alpha } L _ { \alpha } ^ { a ^ { \prime } } { \bf 1 } _ { \alpha } \psi ^ { b ^ { \prime } } ;
$$

(3) At every edge, we place the bivector<sup>4</sup>

$$
V ( z , w ) | _ { \mathcal { H } _ { 1 } \otimes \mathcal { H } _ { 1 } } = L ^ { - 3 } t ^ { N } \sum _ { \alpha , \beta } \sum _ { c , d , s } L _ { \alpha } ^ { 1 + s - c } L _ { \beta } ^ { 1 - s - d } ( V _ { c d } ) ^ { \alpha \beta ; s + 1 } \mathbf { 1 } _ { \alpha } \otimes \mathbf { 1 } _ { \beta } ;
$$

(4) At every vertex of genus $g _ { v }$ with $n _ { v }$ legs, we place the map

$$
\sum _ { \alpha } { L ^ { \frac { N + 3 } { 2 } ( 2 g _ { v } - 2 + n _ { v } ) } \sum _ { s } { \frac { 1 } { s ! } } \operatorname { s t } _ { * } ^ { s } \omega _ { g _ { v } , n _ { v } + s } ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } } ( - , T _ { \alpha } ( \psi ) ^ { s } ) } ,
$$

where

$$
\begin{array} { l } { { \displaystyle T _ { \alpha } ( z ) = z ( \mathbf { 1 } - L ^ { \frac { N + 3 } { 2 } } R ( z ) ^ { - 1 } \mathbf { 1 } ) \vert _ { \mathrm { p t _ { \alpha } } } } } \\ { { \displaystyle \ = \sum _ { m = 1 } ^ { \infty } L _ { \alpha } ^ { - m } ( R _ { m } ) _ { 0 } ^ { \alpha } ( - z ) ^ { m + 1 } \mathbf { 1 } _ { \alpha } } } \end{array}
$$

was defined in [Lei24a, Theorem 3.6] and $\mathrm { s t } ^ { s } \colon \overline { { \mathbb { M } } } _ { g , n + s } \to \overline { { \mathbb { M } } } _ { g , n }$ is the morphism forgetting the last s marked points. Recall from [Lei24a, Lemma 2.4] that

$$
\omega _ { g , n } ^ { \mathrm { p t } _ { \alpha } , \mathrm { t w } } = \bigg ( \frac { 1 } { p _ { k } } N ( - t _ { \alpha } ) ^ { N + 3 } \bigg ) ^ { g - 1 } \Omega _ { g , n } ^ { \mathrm { p t } } .
$$

We will now count the degrees of the contributions at each vertex labeled by $\mathrm { p t } _ { \alpha } .$ Let $L _ { v }$ be the set of ordinary (first $n )$ legs attached to v and $L _ { v } ^ { \prime }$ be the set of special legs attached to v. The factor involving $L _ { \alpha } , L .$ , and $Y$ is

$$
L _ { \alpha } ^ { ( N + 3 ) ( g _ { v } - 1 ) } \prod _ { \ell \in L _ { v } } L _ { \alpha } ^ { a _ { \ell } - c _ { \ell } } \prod _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } L _ { \alpha } ^ { a _ { \ell ^ { \prime } } ^ { \prime } } \prod _ { f = ( e , v ) \atop e \in E _ { v } } t ^ { \frac { N } { 2 } } L _ { \alpha } ^ { \frac { N } { 2 } } L _ { \alpha } ^ { 1 + s _ { f } - c _ { f } } \prod _ { \ell ^ { \prime \prime } \in \mathrm { t a i l s } } L _ { \alpha } ^ { - c _ { \ell ^ { \prime \prime } } }
$$

Using the fact that

$$
\begin{array} { r l } & { \displaystyle \sum _ { \ell ^ { \prime } \in \mathrm { t a i l s } } c _ { \ell ^ { \prime \prime } } + \sum _ { f = ( e , v ) } c _ { f } + \sum _ { \ell \in L _ { v } } c _ { \ell } + b _ { \ell } + \sum _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } b _ { \ell ^ { \prime } } ^ { \prime } = 3 g _ { v } - 3 + n _ { v } } \\ & { \quad \quad \quad e \in E _ { v } } \\ & { \quad \quad \quad \quad \quad \quad = 3 g _ { v } - 3 + | L _ { v } | + | L _ { v } ^ { \prime } | + | E _ { v } | , } \end{array}
$$

the contribution becomes

$$
\begin{array} { r l } & { \quad ( t L ) ^ { N \left( g - 1 + \frac { | E _ { v } | } { 2 } \right) } L _ { \alpha } ^ { 3 g - 3 + n _ { v } + \sum _ { \ell } ( a _ { \ell } - 1 ) + \sum _ { \ell ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime } - 1 ) + \sum _ { f } s _ { f } - \sum _ { \ell } c _ { \ell } - \sum _ { f } c _ { f } - \sum _ { \ell ^ { \prime \prime } } c _ { \ell ^ { \prime \prime } } } } \\ & { = ( t L ) ^ { N \left( g - 1 + \frac { | E _ { v } | } { 2 } \right) } L _ { \alpha } ^ { \sum _ { \ell } ( a _ { \ell } + b _ { \ell } - 1 ) + \sum _ { \ell ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime } + b _ { \ell ^ { \prime } } ^ { \prime } - 1 ) + \sum _ { f } s _ { f } } . } \end{array}
$$

The remaining tail, edge, and leg contributions contribute a degree in X of at most

$$
\begin{array} { c } { { \displaystyle \sum _ { \ell \in L _ { v } } \left( c _ { \ell } + \left\lfloor \frac { a _ { \ell } } { N } \right\rfloor \right) + \displaystyle \sum _ { f = ( e , v ) } \left( c _ { f } + \frac 1 2 \right) + \displaystyle \sum _ { \ell ^ { \prime \prime } \in \mathrm { t a i l s } } c _ { \ell ^ { \prime \prime } } } } \\ { { = 3 g _ { v } - 3 + n _ { v } + \displaystyle \frac { | E _ { v } | } { 2 } + \displaystyle \sum _ { \ell \in L _ { v } } \left\lfloor \frac { a _ { \ell } } { N } \right\rfloor - \displaystyle \sum _ { \ell \in L _ { v } } b _ { \ell } - \displaystyle \sum _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } b _ { \ell ^ { \prime } } ^ { \prime } } } \end{array}
$$

Note that the end result must be independent of the hours α, so we can sum over all α and obtain a multiplicative factor

$$
\begin{array} { r } { L _ { \alpha } ^ { \frac { 1 } { N } } \Bigl ( \sum _ { \ell \in L _ { v } } ( a _ { \ell } + b _ { \ell } - 1 ) + \sum _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime } + b _ { \ell ^ { \prime } } ^ { \prime } - 1 ) + \sum _ { e \in E _ { v } } s _ { ( e , v ) } \Bigr ) } \\ { L _ { \alpha } ^ { \frac { 1 } { N } } \Bigl ( \sum _ { \ell \in L _ { v } } ( a _ { \ell } + b _ { \ell } - 1 ) + \sum _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime } + b _ { \ell ^ { \prime } } ^ { \prime } - 1 ) + \sum _ { e \in E _ { v } } s _ { ( e , v ) } \Bigr ) } \end{array} .
$$

Denote the exponent by $c _ { v }$ . Clearly if this is not an integer, the contribution vanishes after summing over all α. By our choice of indexing of the edge contributions, we see that $s _ { ( e , v _ { 1 } ) } + s _ { ( e , v _ { 2 } ) } = 0$ whenever $e = ( v _ { 1 } , v _ { 2 } )$ . In particular, taking the product over all vertices gives an exponent of

$$
\sum _ { v } c _ { v } = { \frac { 1 } { N } } ( | \mathbf { a } | + | \mathbf { a } ^ { \prime } | + | \mathbf { b } | + | \mathbf { b } ^ { \prime } | - n - m ) = c .
$$

If this is not an integer, the total contribution vanishes.

Multiplying the prefactors over all vertices, we obtain a total prefactor

$$
L _ { \alpha } ^ { N \sum _ { v } r _ { v } } ( t L ) ^ { \sum _ { v } N \left( g _ { v } - 1 + \frac { | E _ { v } | } { 2 } \right) } = ( t L ) ^ { N c + N ( g - 1 ) } .
$$

Using the fact that $Y = L ^ { - N }$ , the prefactor becomes

$$
\left( { \frac { Y } { t ^ { N } } } \right) ^ { - ( g - 1 + c ) } .
$$

Multiplying the remaining contributions from the tails, edges, and legs, the total degree in X is at most

$$
\begin{array} { l } { { \displaystyle \sum _ { v } 3 g _ { v } - 3 + n _ { v } + \frac { | E _ { v } | } { 2 } + \sum _ { \ell \in L _ { v } } \left\lfloor \frac { a _ { \ell } } { N } \right\rfloor - \sum _ { \ell \in L _ { v } } b _ { \ell } - \sum _ { \ell ^ { \prime } \in L _ { v } ^ { \prime } } b _ { \ell ^ { \prime } } ^ { \prime } } } \\ { { \mathrm { } = 3 g - 3 + n + m + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor - | \mathbf { b } | - | \mathbf { b } ^ { \prime } | . } } \end{array}
$$

The desired result follows after applying the normalization factor $\left( { \frac { Y } { t ^ { N } } } \right) ^ { g - 1 + c }$ □

2.4. Vanishing of the [0] theory. We will now study the MSP [0] theory. Unfortunately, we need to factorize the MSP [0] theory to prove the desired polynomiality result, but we will prove a vanishing result similar to the first part of Lemma 2.11.

Definition 2.12. Define the mod-N degrees by $\deg \varphi _ { j } = \deg \phi _ { j } = j$ mod N and deg $\psi = 1$

Lemma 2.13. $R ^ { [ 0 ] } ( z )$ preserves the mod-N degree. If we define ${ \bar { j } } = j$ mod $N ,$ then

$$
R ^ { [ 0 ] } ( z ) ^ { * } \phi _ { j } = c _ { j , k } ^ { \prime } q ^ { \left\lfloor \frac { j } { N } \right\rfloor } \varphi _ { j } ^ { - } + { \cal O } ( z ^ { \overline { { j } } - 3 } )
$$

f $\dot { o r } j = 0 , \dots , N + 3$ , where we $d e f i n e ^ { 5 }$

$$
\begin{array} { r l } & { c _ { j , 6 } ^ { \prime } = ( 1 , \dots , 1 , - 3 6 0 , - 3 1 3 2 , - 8 5 3 2 , - 1 1 3 0 4 ) } \\ & { c _ { j , 8 } ^ { \prime } = ( 1 , \dots , 1 , - 1 6 8 0 , - 1 7 4 8 8 , - 4 8 0 4 8 , - 6 3 8 5 6 ) } \\ & { c _ { j , 1 0 } ^ { \prime } = ( 1 , \dots , 1 , - 1 5 1 2 0 , - 1 9 4 6 4 0 , - 6 0 5 3 6 0 , - 7 8 4 8 8 0 ) . } \end{array}
$$

Proof. Recall that

$$
z D R ^ { [ 0 ] } ( z ) ^ { * } = R ^ { [ 0 ] } ( z ) ^ { * } A ^ { M } - A ^ { Z } R ^ { [ 0 ] } ( z ) ^ { * } ,
$$

where

$$
A ^ { Z } = \left( \begin{array} { c c c c } { { 0 } } & { { } } & { { } } & { { } } \\ { { I _ { 1 1 } } } & { { 0 } } & { { } } & { { } } \\ { { } } & { { I _ { 2 2 } } } & { { 0 } } & { { } } \\ { { } } & { { } } & { { I _ { 1 1 } } } & { { 0 } } \end{array} \right)
$$

and $A ^ { M }$ is given by the formulae

$$
A _ { j + 1 , j } ^ { M } = 1 , \qquad A _ { j + N - 1 , j } ^ { M } = c _ { j , k } q - \delta _ { i , 4 } t ^ { N }
$$

and all other entries being zero, where

$$
\begin{array} { r l } & { c _ { j , 6 } ^ { \prime } = ( 3 6 0 , 2 7 7 2 , 5 4 0 0 , 2 7 7 2 , 3 6 0 ) } \\ & { c _ { j , 8 } ^ { \prime } = ( 1 6 8 0 , 1 5 8 0 8 , 3 0 5 6 0 , 1 5 8 0 8 , 1 6 8 0 ) } \\ & { c _ { j , 1 0 } ^ { \prime } = ( 1 5 1 2 0 , 1 7 9 5 2 0 , 4 1 0 7 2 0 , 1 7 9 5 2 0 , 1 5 1 2 0 ) . } \end{array}
$$

The expression for $R ^ { [ 0 ] } \phi _ { j }$ follows directly. The fact that $R ^ { [ 0 ] }$ preserves the mod-N degree follows from the fact that

$$
R ^ { [ 0 ] } ( z ) ^ { - 1 } x = S ^ { Z } ( q ^ { \prime } , z ) ( S ^ { M } ( z ) ^ { - 1 } x ) | _ { Z }
$$

for all $x \in \mathcal { H } _ { Z }$ and the fact that both $S ^ { Z }$ and $S ^ { M }$ preserve the mod-N degrees. Here, it is helpful to recall that

$$
\begin{array} { c } { { S ^ { Z } ( z ) ^ { * } = I + \displaystyle \frac { 1 } { z } \left( { \begin{array} { l l l l } { { 0 } } & { { } } & { { } } & { { } } \\ { { J _ { 1 } ^ { \prime } } } & { { 0 } } & { { } } & { { } } \\ { { } } & { { J _ { 2 } ^ { \prime } } } & { { 0 } } & { { } } \\ { { } } & { { } } & { { J _ { 1 } ^ { \prime } } } & { { 0 } } \end{array} } \right) } } \\ { { + \displaystyle \frac { 1 } { z ^ { 2 } } \left( { \begin{array} { l l l l } { { 0 } } & { { } } & { { } } & { { } } \\ { { J _ { 2 } } } & { { } } & { { 0 } } & { { } } \\ { { } } & { { \frac { J _ { 2 } ^ { \prime } } { J _ { 1 } ^ { \prime } } J _ { 1 } - J _ { 2 } } } & { { } } & { { 0 } } \end{array} } \right) + \displaystyle \frac { 1 } { z ^ { 3 } } \left( { \begin{array} { l l l l } { { 0 } } & { { } } & { { } } & { { } } \\ { { } } & { { 0 } } & { { } } \\ { { J _ { 3 } } } & { { } } & { { 0 } } & { { } } \\ { { J _ { 3 } } } & { { } } & { { } } & { { 0 } } \end{array} } \right) , } } \end{array}
$$

where we define $\begin{array} { r } { J _ { b } = { \frac { I _ { b } } { I _ { 0 } } } , J _ { 1 } ^ { \prime } = I _ { 1 1 } } \end{array}$ , and ${ { J } _ { 2 } ^ { \prime } } = { { J } _ { 1 } } + D J _ { 2 }$

Lemma 2.14. Define $\begin{array} { r } { c : = \frac 1 N ( | { \bf a } | + | { \bf b } | - n ) } \end{array}$ . If c /∈ Z, then $f _ { g , ( { \bf a } , { \bf b } ) } ^ { [ 0 ] } = 0$

Proof. Recall that $\Omega ^ { [ 0 ] } = R ^ { [ 0 ] } . \Omega ^ { Z , \mathrm { t w } }$ is defined by a graph sum formula, where the vertex, edge and leg contributions are given by the following:

• At each leg with insertion $\phi _ { a } \psi ^ { b }$ , we place $R ^ { [ 0 ] } ( - \psi ) ^ { * } \phi _ { a } \psi ^ { b }$

• At each edge, we place the bivector

$$
\sum _ { j = 0 } ^ { N + 3 } \frac { \phi _ { j } \otimes \phi ^ { j } - R ^ { [ 0 ] } ( - z ) ^ { * } \phi _ { j } \otimes R ^ { [ 0 ] } ( - w ) ^ { * } \phi ^ { j } } { z + w } ;
$$

• At each vertex, we place the linear map $I _ { 0 } ( q ^ { \prime } ) ^ { - ( 2 g - 2 + n ) } \Omega _ { g , n } ^ { Z , \mathrm { t w } , \tau _ { Z } ( q ^ { \prime } ) } ( - )$ Because $\phi _ { j } \otimes \phi ^ { j }$ has mod-N degree 3 and $R ^ { [ 0 ] }$ preserves the mod-N degree, we see that the edge contributions have mod-N degree 2. Then note that for • being either $\mathrm { } ^ { \mathrm { * } } Z ^ { \mathrm { * } } \ \mathrm { o r } \ \mathrm { } ^ { \mathrm { * } } Z , \mathrm { \bar { t w } } ^ { \mathrm { * } }$ the integral

$$
\int _ { \overline { { \mathcal { M } } } _ { g , m } } \Omega _ { g , m } ^ { \bullet } \left( \bigotimes _ { j = 1 } ^ { m } \varphi _ { a _ { j } } \psi ^ { b _ { j } } \right)
$$

vanishes unless $\textstyle \sum _ { j = 1 } ^ { m } ( a _ { j } + b _ { j } ) = m$ . Summing over all vertices and edges in an arbitrary stable graph, we see that the contribution can only be nonzero if

$$
\sum _ { i = 1 } ^ { n } ( { \bar { a } } _ { i } + { \bar { b } } _ { i } ) = n ,
$$

which is equivalent to $c \in \mathbb { Z }$

We may now assume that $\begin{array} { r } { c : = \frac 1 N ( | \mathbf a | + | \mathbf b | - n ) } \end{array}$ is an integer.

Lemma 2.15. Define

$$
\bar { c } : = \frac { \lvert \bar { \mathbf { a } } \rvert + \lvert \mathbf { b } \rvert - n } { N } .
$$

$I f N \gg 3 g - 3 + 3 n$ , we always have $\bar { c } \geq 0$ . In addition, $i f \bar { c } \neq 0$ , then $f _ { g , ( { \bf a } , { \bf b } ) } ^ { [ 0 ] } = 0$

Proof. Using the assumption that $N > 3 g - 3 + 3 n$ and the fact that ${ \overline { { \mathcal { M } } } } _ { g , n }$ is a DM stack (hence $3 g - 3 + n \geq 0 )$ , we obtain $N > 2 n$ . Because all $a _ { i } , b _ { i } \geq 0$ and ¯c is an integer, we must have

$$
\bar { c } \geq \left\lceil \frac { - n } { N } \right\rceil = 0 .
$$

The vanishing result is another degree-counting argument. Assume that $\bar { c } > 0$ Recall $f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 ] }$ is a sum of stable graph contributions, where we place

$$
R ^ { [ 0 ] } ( - \psi ) ^ { * } \phi _ { a _ { i } } \psi ^ { b _ { i } }
$$

at the i-th leg. In particular, the total degree of the ancestors is at least

$$
\begin{array} { c } { \left| { \bar { \mathbf { a } } } \right| - 3 n + \left| \mathbf { b } \right| = N \bar { c } - \left( \left| \mathbf { b } \right| - n \right) - 3 n + b } \\ { \geq N - 2 n . } \end{array}
$$

However, the contribution vanishes if

$$
| \bar { \mathbf { a } } _ { v } | - 3 ( n _ { v } - | E _ { v } | ) + | \mathbf { b } _ { v } | > 3 g _ { v } - 3 + n _ { v }
$$

and therefore if

$$
\begin{array} { r } { | \bar { \mathbf { a } } | - 3 n + | \mathbf { b } | > \displaystyle \sum _ { v } ( 3 g _ { v } - 3 + n _ { v } ) } \\ { = 3 g - 3 + n - | E | . } \end{array}
$$

However, by assumption, we see that

$$
\begin{array} { r l } { | \bar { \mathbf { a } } | - 3 n + | \mathbf { b } | \geq N - 2 n } \\ { > 3 g - 3 + n } \\ { \geq 3 g - 3 + n - | E | , } \end{array}
$$

so all graph contributions must vanish.

Corollary 2.16. $I f ~ f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 ] }$ is nonzero, then $c = \left\lfloor { \frac { \mathbf { a } } { N } } \right\rfloor$ and

$$
g - 1 + c \leq 3 g - 3 + c + n - | \mathbf { b } | .
$$

Definition 2.17. Define the MSP [0] potential with special insertions by

$$
f _ { g , ( { \mathbf a } , { \mathbf b } ) , ( { \mathbf a } ^ { \prime } , { \mathbf b } ^ { \prime } ) } ^ { [ 0 ] } : = \int _ { \overline { { \mathcal { M } } } _ { g , n } } \Omega _ { g , n + m } ^ { [ 0 ] } \left( \bigotimes _ { i = 1 } ^ { n } \phi _ { a _ { i } } \psi ^ { b _ { i } } , \bigotimes _ { j = 1 } ^ { m } E _ { a _ { j } ^ { \prime } , b _ { j } ^ { \prime } } { ( \psi _ { n + j } ) } \right) ,
$$

where we define

$$
E _ { a ^ { \prime } , b ^ { \prime } } ( \psi ) = L ^ { - a ^ { \prime } } \cdot [ w ^ { b ^ { \prime } } ] \frac { ( R ( \psi ) - R ( - w ) ) \bar { \phi } ^ { a ^ { \prime } } } { \psi + w } .
$$

Here, $[ w ^ { b ^ { \prime } } ]$ means that we take the coeficient of $w ^ { b ^ { \prime } }$ in the expression.

By construction, we have

$$
V ^ { 0 1 } ( z , w ) = \sum _ { a = 1 } ^ { N } E _ { a b } ( z ) w ^ { b } \otimes L ^ { a } R ( w ) \bar { \phi } _ { a } .
$$

Lemma 2.18. $I f a - m \not \equiv b$ (mod $N )$ , then $( \phi _ { a } , R _ { m } \bar { \phi } ^ { b } ) = 0$ . In the case when $a - m \equiv b$ (mod N), then

$$
L ^ { - a + m } ( \phi _ { a } , R _ { m } \bar { \phi } ^ { b } ) \in \mathbb { Q } ( t ^ { N } ) [ X ] _ { m + \left\lfloor \frac { a } { N } \right\rfloor } .
$$

Proof. Note that

$$
\begin{array} { c } { { ( \phi _ { a } , R _ { m } \bar { \phi } ^ { b } ) = \displaystyle \sum _ { \alpha = 1 } ^ { N } L _ { \alpha } ^ { - b } ( \phi _ { a } , R _ { m } \bar { \bf 1 } ^ { \alpha } ) } } \\ { { = \displaystyle \sum _ { \alpha = 1 } ^ { N } L _ { \alpha } ^ { - b } L ^ { a - m } ( R _ { m } ) _ { a } ^ { \alpha } . } } \end{array}
$$

The result follows by using Lemma 2.8 and the the fact that the total power of the roots of unity is $a - m - b$ □

Lemma 2.19. The [0] potential with special insertions $f _ { g , ( { \mathbf a } , { \mathbf b } ) , ( { \mathbf a } ^ { \prime } , { \mathbf b } ^ { \prime } ) } ^ { [ 0 ] }$ vanishes unless $\begin{array} { r } { c : = \frac { | \mathbf { a } | + | \mathbf { b } | + \left| \mathbf { a } ^ { \prime } \right| + \left| \mathbf { b } ^ { \prime } \right| - n + m } { N } \in \mathbb { Z } . } \end{array}$

Proof. Write

$$
R _ { m } \bar { \phi } ^ { b } = \sum _ { s = 1 } ^ { N + 3 } ( R _ { m } \bar { \phi } ^ { b } , \phi _ { s } ) \phi ^ { s } .
$$

By the previous lemma, the only nonzero terms are the ones with $s \equiv m + b ($ (mod N)), so the mod-N degree of $R _ { m } \bar { \phi } ^ { b }$ is $3 - ( m + b )$ . This implies that the mod-N degree of $E _ { a b }$ is $2 - \left( a + b \right)$ . Computing the total ancestor degree at all vertices as in the proof of Lemma 2.15, we obtain the desired result. □

## 3. The A-model Feynman rule

In order to extract information from the [0] theory, we will extract a part of it which satisfies an X-polynomiality property.

3.1. Factorization of the [0] theory.

Definition 3.1. Define the CohFT<sup>6</sup> $\Omega ^ { \mathbf { A } , \mathbb { G } }$ by the formula

$$
\Omega ^ { \mathbf { A } , \mathbb { G } } = R ^ { \mathbf { A } , \mathbb { G } } . \Omega ^ { Z , \mathrm { t w } } .
$$

Also, define the generating function

$$
f _ { g , ( { \mathbf a } , { \mathbf b } ) } ^ { { \mathbf A } , \mathbb { G } } : = \left( \frac { - p _ { k } Y } { t ^ { N } } \right) ^ { g - 1 } \int _ { \overline { { \mathcal { M } } } _ { g , n } } \Omega _ { g , n } ^ { { \mathbf A } , \mathbb { G } } ( \varphi _ { a _ { 1 } } \psi _ { 1 } ^ { b _ { 1 } } , \dots , \varphi _ { a _ { n } } \psi _ { n } ^ { b _ { n } } ) .
$$

Remark 3.2. Because the CohFT $\Omega ^ { Z }$ and $\Omega ^ { \mathbf { A } }$ have diferent units, the graph sum formula for the $R ^ { \mathbf { A } }$ action will have $T = z ( 1 - I _ { 0 } )$ , which by the dilaton equation will imply that we place the linear map

$$
\frac { 1 } { I _ { 0 } ^ { 2 g - 2 + n } } \Omega _ { g , n } ^ { Z }
$$

at each vertex.

Remark 3.3. Because the basis $\varphi _ { 0 } , \ldots , \varphi _ { 3 }$ is not flat, we will need to consider the transformation

$$
\Psi : = \left( \begin{array} { c c c c } { { I _ { 0 } } } & { { } } & { { } } & { { } } \\ { { } } & { { I _ { 0 } I _ { 1 1 } } } & { { } } & { { } } \\ { { } } & { { } } & { { I _ { 0 } I _ { 1 1 } I _ { 2 2 } } } & { { } } \\ { { } } & { { } } & { { } } & { { I _ { 0 } I _ { 1 1 ^ { 2 } } I _ { 2 2 } } } \end{array} \right)
$$

from this basis to the flat basis $1 , H , H ^ { 2 } , H ^ { 3 }$ . In particular, if we want to compute derivatives of $R ^ { \mathbf { A } , \mathbb { G } }$ , then we will need the input basis to be the flat basis, and in this basis $R ^ { \mathbf { A } , \mathbb { G } } ( z ) ^ { - 1 }$ takes the form

$$
\begin{array} { r } { \Psi \left( \ b { I } - \left( \begin{array} { c c c c } { 0 } & { z E _ { \psi } ^ { \mathbb { G } } } & { z ^ { 2 } E _ { \varphi \psi } ^ { \mathbb { G } } } & { z ^ { 3 } E _ { 1 \psi ^ { 2 } } ^ { \mathbb { G } } } \\ { 0 } & { z E _ { \varphi \varphi } ^ { \mathbb { G } } } & { z ^ { 2 } E _ { 1 \varphi \psi } ^ { \mathbb { G } } } \\ & & { 0 } & { z E _ { \psi } ^ { \mathbb { G } } } \\ & & & { 0 } \end{array} \right) \right) . } \end{array}
$$

Definition 3.4. Define the matrix

$$
R ^ { X } ( z ) : = R ^ { \mathbf { A } } ( z ) ^ { - 1 } \cdot R ^ { [ 0 ] } ( z ) .
$$

We will consider the input basis of $R ^ { X }$ to be $\varphi _ { 0 } , \ldots , \varphi _ { 3 }$ and the output basis to be $\phi _ { 0 } , \ldots , \phi _ { N + 3 }$

Lemma 3.5. The matrix elements $( R _ { m } ^ { X } ) _ { j } ^ { a } : = ( \phi _ { j } , R _ { m } ^ { X } \varphi ^ { a } )$ of $R ^ { X }$ satisfy the following whenever m $< N - 3$ :

(1) $I f j \not \equiv m + a$ (mod N), then $( R _ { m } ^ { X } ) _ { j } ^ { a } = 0 ,$

(2) $I f j < N$ , then $( R _ { m } ^ { X } ) _ { j } ^ { a } \in X \mathbb { Q } [ X ] _ { m - 1 } ;$

(3) $I f j \geq N$ , then $( R _ { m } ^ { X } ) _ { j } ^ { a } \in q \mathbb { Q } [ X ] _ { m } ;$

(4) We have $R ^ { X } ( - z ) ^ { * } C ^ { X } ( z ) = \operatorname { I d } _ { \mathcal { H } _ { Z } }$ for some $C ^ { X } ( z )$ of the form $\binom { C ( z ) } { 0 }$ , where C(z) has the form

$$
C ( z ) = \left( \begin{array} { c c c c } { { 1 } } & { { z \cdot C _ { 1 } } } & { { z ^ { 2 } \cdot C _ { 2 } } } & { { z ^ { 3 } \cdot C _ { 3 } } } \\ { { 0 } } & { { 1 } } & { { z \cdot C _ { 4 } } } & { { z ^ { 2 } \cdot C _ { 5 } } } \\ { { 0 } } & { { 0 } } & { { 1 } } & { { z \cdot C _ { 6 } } } \\ { { 0 } } & { { 0 } } & { { 0 } } & { { 1 } } \end{array} \right)
$$

for some $C _ { 1 } , C _ { 2 } , C _ { 4 } , C _ { 6 } \in \mathbb { Q } [ X ] _ { 1 }$ <sub>1</sub> and $C _ { 3 } , C _ { 5 } \in \mathbb { Q } [ X ] _ { 2 }$

Proof. Using the equation

$$
z D R ^ { [ 0 ] } ( z ) ^ { * } = R ^ { [ 0 ] } ( z ) ^ { * } A ^ { M } - A ^ { Z } R ^ { [ 0 ] } ( z ) ^ { * } .\tag{3.1}
$$

Using the definition $R ^ { [ 0 ] } ( z ) ^ { * } = R ^ { \mathbf { A } } ( z ) ^ { * } R ^ { X } ( z ) ^ { * }$ , we obtain

$$
z D ( R ^ { \bf A } ( z ) ^ { * } R ^ { X } ( z ) ^ { * } ) = R ^ { \bf A } ( z ) ^ { * } R ^ { X } ( z ) ^ { * } A ^ { M } - A ^ { Z } R ^ { \bf A } ( z ) ^ { * } R ^ { X } ( z ) ^ { * } ,
$$

and multiplying by $R ^ { \bf A } ( - z )$ , we obtain

$$
\begin{array} { r } { { R } ^ { X } ( z ) ^ { * } { A } ^ { M } = z { D } ( { R } ^ { X } ( z ) ^ { * } ) + { R } ^ { \bf A } ( - z ) [ ( z { D } + { A } ^ { Z } ) { R } ^ { \bf A } ( z ) ^ { * } ] { R } ^ { X } ( z ) ^ { * } . } \end{array}\tag{3.2}
$$

Direct computation (here, note that the basis $\varphi _ { 0 } , \ldots , \varphi _ { 3 }$ is not flat, so we need the version of $\bar { R } ^ { \mathbf { A } }$ with the Ψ) yields

$$
\begin{array} { r } { R ^ { { \bf A } } ( - z ) [ ( z D + A ^ { Z } ) R ^ { { \bf A } } ( z ) ^ { * } ] = \left( \begin{array} { c c c c } { 0 } & { 0 } & { 0 } & { - r _ { 1 } X z ^ { 4 } } \\ { 1 } & { 0 } & { - r _ { 0 } X z ^ { 2 } } & { 0 } \\ { 0 } & { 1 } & { - X z } & { 0 } \\ { 0 } & { 0 } & { 1 } & { - X z } \end{array} \right) . } \end{array}
$$

Therefore, we can compute $R ^ { X } ( z ) ^ { * } \phi _ { i }$ from $R ^ { X } ( z ) ^ { * } \phi _ { 0 }$ . Because $R ^ { [ 0 ] } ( z ) ^ { * } \phi _ { 0 } = \varphi _ { 0 } +$ $O ( z ^ { N - 3 } )$ and $R ^ { \mathbf { A } } ( z ) ^ { * } \varphi _ { 0 } = \varphi _ { 0 }$ , the first entry of $R ^ { X }$ is $1 + O \big ( z ^ { N - 3 } \big )$

We then note that the matrices $A ^ { M }$ and $R ^ { \bf { \dot { A } } } ( - z ) [ ( z D + A ^ { Z } ) R ^ { \bf { A } } ( z ) ^ { * } ]$ both increase the mod-N degree by 1. Therefore, we see that $R ^ { X }$ preserves the mod-N degree, so the vanishing property holds. The degree estimates follow from the explicit formulae for $A ^ { M }$ and $\mathbf { \bar { \Sigma } } R ^ { \mathbf { A } } ( - z ) [ ( z D + A ^ { z } ) R ^ { \mathbf { A } } ( { \bar { z } } ) ^ { * } ]$ . The final statement is obtained by direct computation. □

Corollary 3.6. The edge contribution

$$
V _ { X } : = \frac { \sum _ { i = 0 } ^ { 3 } \varphi _ { i } \otimes \varphi ^ { i } - \sum _ { j = 0 } ^ { N + 3 } R ^ { X } ( - z ) ^ { \ast } \phi _ { j } \otimes R ^ { X } ( - w ) ^ { \ast } \phi ^ { j } } { z + w }
$$

satisfies the degree bound

$$
\frac { Y } { t ^ { N } } [ z ^ { m _ { 1 } } w ^ { m _ { 2 } } ] V _ { X } \in \mathcal { H } _ { Z } ^ { \otimes 2 } [ X ] _ { m _ { 1 } + m _ { 2 } + 1 } .
$$

Proof. This follows from the lemma and the fact that $\begin{array} { r } { \varphi _ { j } = \frac { t ^ { N } } { p _ { k } Y } \varphi _ { 3 - j } } \end{array}$

3.2. Polynomiality of the [0] theory and the A theory. We now prove the polynomiality of the [0]-theory. First, we will prove some lemmas about $E _ { a ^ { \prime } , b ^ { \prime } } ( z )$ which was introduced in Definition 2.17.

Lemma 3.7. Recall the definition of $E _ { a ^ { \prime } , b ^ { \prime } } ( z )$ from Definition 2.17. Then

$$
( \phi ^ { a } , [ z ^ { b } ] E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) = 0
$$

unless $a + a ^ { \prime } + b + b ^ { \prime } \equiv 2$ (mod N).

Proof. By definition, we have

$$
\begin{array} { l } { { ( \phi _ { a } , [ z ^ { b } ] E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) = ( - 1 ) ^ { b ^ { \prime } } ( \phi _ { a } , R _ { b + b ^ { \prime } + 1 } \bar { \phi } ^ { a ^ { \prime } } ) } } \\ { { { } } } \\ { { { } = ( - 1 ) ^ { b ^ { \prime } } \displaystyle \sum _ { \alpha } { \cal L } _ { \alpha } ^ { - a ^ { \prime } } ( \phi _ { a } , R _ { b + b ^ { \prime } + 1 } \bar { { \bf 1 } } ^ { \alpha } ) , } } \end{array}
$$

which vanishes unless $a - a ^ { \prime } - ( b + b ^ { \prime } + 1 ) \equiv 0 { \pmod { N } }$ . The result follows from the fact that $\phi ^ { a }$ has mod-N degree $3 - a$ □

Lemma 3.8. Whenever $N \gg b ^ { \prime \prime }$ , then

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { - c _ { E } } \cdot [ z ^ { b ^ { \prime \prime } } ] ( \varphi ^ { a ^ { \prime \prime } } , R ^ { X } ( - z ) ^ { \ast } E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) \in \mathbb { Q } [ X ] _ { b ^ { \prime } + b ^ { \prime \prime } + 1 } ,
$$

where we define $\begin{array} { r } { c _ { E } : = \frac { a ^ { \prime } + b ^ { \prime } + a ^ { \prime \prime } + b ^ { \prime \prime } - N - 2 } { N } } \end{array}$ $I f c _ { E } \notin \mathbb { Z }$ , then the above quantity vanishes.

Proof. The vanishing is a corollary of Lemma 3.5 and Lemma 3.7. The degree estimate comes from the following considerations.

Whenever $a = 4 , \dots , N - 1$ and $m ^ { \prime } < N - 3$ , then $( \varphi ^ { a ^ { \prime \prime } } , [ z ^ { m ^ { \prime } } ] R ^ { X } ( - z ) ^ { * } \phi _ { a } )$ is nonzero only if $a = a ^ { \prime \prime } + m ^ { \prime }$ . If this is satisfied, then it has degree $m ^ { \prime }$ in $X$ , and therefore

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { - c _ { E } } \cdot [ z ^ { b ^ { \prime \prime } } ] ( \varphi ^ { a ^ { \prime \prime } } , R ^ { X } ( - z ) ^ { * } \phi _ { a } ) ( \phi ^ { a } , E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) \in \mathbb { Q } [ X ] _ { b ^ { \prime } + b ^ { \prime \prime } + 1 } .
$$

Here, we use the fact that

$$
[ z ^ { b } ] ( \phi ^ { a } , E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) = \frac { N } { p _ { k } } \bigg ( \frac { Y } { t ^ { N } } \bigg ) ^ { c _ { E } } ( - 1 ) ^ { b ^ { \prime } } ( R _ { b + b ^ { \prime } + 1 } ) _ { N + 3 - a } ^ { \alpha } \in \bigg ( \frac { Y } { t ^ { N } } \bigg ) ^ { c _ { E } } \mathbb { Q } [ X ] _ { b + b ^ { \prime } + 1 }
$$

by Lemma 2.8 because $\begin{array} { r } { \lfloor \frac { a } { N } \rfloor = 0 } \end{array}$

In the case where $a = 0 , \ldots , 3 .$ , then for any $m ^ { \prime } < N - 3$ , the vanishing still holds, so we use $\phi ^ { a } = { \textstyle \frac { 1 } { 5 } } ( \phi _ { N + 3 - a } - t ^ { N } \phi _ { 3 - a } )$ to compute. The $\phi _ { N + 3 - a }$ term contributes an element of $\mathbb { Q } [ X ] _ { b ^ { \prime } + b ^ { \prime \prime } + 2 }$ , whereas the $t ^ { N } \phi _ { 3 - a }$ term contributes

$$
[ z ^ { b } ] ( t ^ { N } \phi _ { 3 - a } , E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) = N ( - 1 ) ^ { b ^ { \prime } } \left( \frac { Y } { t ^ { N } } \right) ^ { c _ { E } } ( R _ { b + b ^ { \prime } + 1 } ) _ { 3 - a } ^ { \alpha } Y .
$$

Therefore, we have

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { - c _ { E } } \cdot [ z ^ { b ^ { \prime \prime } } ] ( \varphi ^ { a ^ { \prime \prime } } , R ^ { X } ( - z ) ^ { * } \phi _ { a } ) ( \phi ^ { a } , E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) \in \mathbb { Q } [ X ] _ { b ^ { \prime } + b ^ { \prime \prime } + 2 } .
$$

In the case when $a \geq N$ , the nonvanishing condition becomes $a - N = a ^ { \prime \prime } + m ^ { \prime }$ Therefore, Lemma 3.5 implies that

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { - c _ { E } } \cdot [ z ^ { b ^ { \prime \prime } } ] ( \varphi ^ { a ^ { \prime \prime } } , R ^ { X } ( - z ) ^ { * } \phi _ { a } ) ( \phi ^ { a } , E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) \in q \mathbb { Q } [ X ] _ { b ^ { \prime } + b ^ { \prime \prime } + 1 } .
$$

If we sum the contributions from the above procedure, the degree count is too high by 1. The $X ^ { b ^ { \prime } + b ^ { \prime \prime } + 2 }$ -coeficient is given by (up to a constant)

$$
[ X ^ { b ^ { \prime } + b ^ { \prime \prime } + 2 } ] \sum _ { \stackrel { \scriptstyle i + j = b ^ { \prime } + b ^ { \prime \prime } + 1 } { \scriptstyle \frac { j \le b ^ { \prime \prime } } { \scriptstyle a < 3 } } } ( R _ { j } ^ { X } ) _ { i } ^ { a } ( R _ { i } ) _ { N + 3 - a } - Y ( R _ { j } ^ { X } ) _ { i } ^ { a } ( R _ { i } ) _ { 3 - a } + \frac { Y } { { \scriptstyle t ^ { N } } } ( R _ { j } ^ { X } ) _ { i } ^ { N + a } ( R _ { i } ) _ { 3 - a } .
$$

Note that the MSP quantum connection (3.1) (in particular the value of $A ^ { M } )$ implies that $\begin{array} { r } { [ X ^ { m + 1 } ] ( R _ { m } ) _ { j } = \frac { c _ { j , k } ^ { \prime } } { r } \cdot [ X ^ { m } ] ( R _ { m } ) _ { j - N } } \end{array}$ and the equation (3.2) for $R ^ { X }$ implies that $[ X ^ { m } ] ( q ^ { - 1 } ( { \cal R } _ { m } ^ { X } ) _ { j } ^ { a } ) \stackrel { . } { = } c _ { j , k } ^ { \prime } \cdot [ X ^ { m } ] ( { \cal R } _ { m } ) _ { j - N } ^ { a }$ , where $\boldsymbol { c } _ { j , \boldsymbol { k } } ^ { \prime }$ was defined in Lemma 2.13.

This implies that

$$
\begin{array} { l } { { [ { \cal X } ^ { i + j + 1 } ] ( ( R _ { j } ^ { X } ) _ { i } ^ { a } ( R _ { i } ) _ { N + 3 - a } - Y ( R _ { j } ^ { X } ) _ { i } ^ { a } ( R _ { i } ) _ { 3 - a } + \displaystyle \frac { Y } { t ^ { N } } ( R _ { j } ^ { X } ) _ { i } ^ { N + a } ( R _ { i } ) _ { 3 - a } ) } } \\ { { = \displaystyle \left( 1 + \displaystyle \frac { c _ { N + a } ^ { \prime } } { r } + \displaystyle \frac { c _ { N + 3 - a } ^ { \prime } } { r } \right) } } \\ { { = 0 } } \end{array}
$$

for all $i + j = b ^ { \prime } + b ^ { \prime \prime } + 1$ and $a = 0 , 1 , 2 , 3$ , where we have used the fact that $c _ { N + a } ^ { \prime } + c _ { N + 3 - a } ^ { \prime } = - r ,$ , which is implied by the fact that $I _ { 0 } ^ { 2 } I _ { 1 1 } ^ { 2 } I _ { 2 2 } = Y$ □

We will now put a partial ordering on the set of pairs $( g , n )$ such that $( h , m ) \prec$ $( g , n ) { \mathrm { ~ i f ~ } } ( h , m ) < ( g , n )$ in the lexicographic order and $3 h + m \leq 3 g + n$ . We will use induction on $( h , m )$ under this ordering and a bootstrapping argument to prove both the polynomiality of the [0] theory and of the A theory.

We introduce the following statements:

(1) Denote by $\mathfrak { P } _ { g , n }$ the statement “for all $\mathbf { a } \in \{ 0 , 1 , 2 , 3 \} ^ { n }$ and b $\in \mathbb { Z } _ { \geq 0 } ^ { n }$ , we have

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { g - 1 } f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 ] } \in \mathbb { Q } [ X ] _ { 3 g - 3 + n - | \mathbf { b } | } . \mathrm { } ,
$$

(2) Denote by $\mathfrak { Q } _ { g , s }$ the statement “for all $m + n \le s , \mathbf { a } \in \{ 0 , \dots , N + 3 \} ^ { m }$ $( \mathbf { b } , \mathbf { b } ^ { \prime } ) \in \mathbb { Z } _ { \geq 0 } ^ { m + \bar { n } }$ , and $\mathbf { a } ^ { \prime } \in \{ 1 , \ldots , N \} ^ { n }$ 2

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { g - 1 } f _ { g , ( { \mathbf a } , { \mathbf b } ) , ( { \mathbf a } , { \mathbf b ^ { \prime } } ) } ^ { [ 0 ] } \in \mathbb { Q } [ X ] _ { 3 g - 3 + m + 2 n + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor - | { \mathbf b } | + | { \mathbf b ^ { \prime } } | } \mathrm { . } ,
$$

Lemma 3.9. Suppose that $\mathfrak { P } _ { h , m }$ holds for all $( h , m ) \prec ( g , n )$ . Then for all $( h , m ) \prec$ $( g , n )$ , we have

$$
f _ { h , ( { \bf a } , { \bf b } ) } ^ { { \bf A } } \in \mathbb { Q } [ X ] _ { 3 h - 3 + m - | { \bf b } | }
$$

for all $\mathbf { a } \in \{ 0 , 1 , 2 , 3 \} ^ { m }$

Proof. First, note that $R ^ { \mathbb { A } }$ preserves degrees, so we must have $\textstyle \sum _ { i } ( a _ { i } + b _ { i } ) = n$ . Now define

$$
\tilde { f } _ { h , ( { \mathbf a } , { \mathbf b } ) } ^ { [ 0 ] } : = \int _ { \overline { { \mathfrak { M } } } _ { h , m } } ( R ^ { X } . \Omega ^ { \mathbf { A } } ) _ { h , m } ( C ^ { X } ( \psi _ { 1 } ) \varphi _ { a _ { 1 } } \psi ^ { b _ { 1 } } , \dots , C ^ { X } ( \psi _ { m } ) \varphi _ { a _ { m } } \psi ^ { b _ { m } } ) .
$$

By the assumption $\mathfrak { P } _ { h , m }$ and the fact that $C ^ { X }$ has nonzero entries only in the top four rows, preserves the mod-N degree, and the fact that $( \phi ^ { j } , C _ { \ell } ^ { X } \varphi _ { a } ) \in \mathbb { Q } [ X ] _ { \ell } .$ , we see that

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { h - 1 } \tilde { f } _ { h , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 ] } \in \mathbb { Q } [ X ] _ { 3 h - 3 + m - | \mathbf { b } | } .
$$

In the graph sum formula for the action of $R ^ { X }$ and $\Omega ^ { \mathbf { A } }$ , we see there is a graph with a single genus $h$ vertex with m insertions (corresponding to the largest stratum of $\overline { { \mathcal { M } } } _ { h , m } )$ . The contribution of this graph is $f _ { h , ( { \bf a } , { \bf b } ) } ^ { { \bf A } }$ . The contribution of any other graph will have the form

$$
\bigotimes _ { v } f _ { g _ { v } , n _ { v } } ^ { \mathbf { A } } \left( \bigotimes _ { i = 1 } ^ { m } \varphi _ { a _ { i } } \psi ^ { b _ { i } } \otimes \bigotimes _ { e } V _ { X } ( e ) \right) ,
$$

where $V _ { X } ( e )$ was defined in Corollary 3.6.

We will now induct on $( h , m )$ . In the base case $( h , m ) = ( 0 , 3 )$ , the leading graph is the only graph, so the result follows directly (note here the diferent normalization conventions for $f ^ { \mathbf { A } }$ and $f ^ { [ 0 ] } )$ . Now we assume the result for all $\left( h ^ { \prime } , m ^ { \prime } \right) \prec \left( h , m \right)$ Using the graph sum, we now count the degrees of all of the contributions.

• The total exponent of $\frac { Y } { t ^ { N } }$ is $\begin{array} { r } { \sum _ { v } ( g _ { v } - 1 ) + | E | = h - 1 } \end{array}$ using Corollary 3.6 and distributing the factors of Y as in the proof of [Lei24a, Theorem 6.1];

• The total degree in X is at most

$$
\begin{array} { l } { { \displaystyle \sum _ { v } \Biggl ( 3 g _ { v } - 3 + n _ { v } - \sum _ { e \in E _ { v } } b _ { ( e , v ) } - \sum _ { i \in L _ { v } } b _ { i } \Biggr ) + \sum _ { e } \bigl ( b _ { ( e , v _ { 1 } ) } + b _ { ( e , v _ { 2 } ) } + 1 \bigr ) } } \\ { { \displaystyle = 3 \Biggl ( \sum _ { v } g _ { v } - | V | + 3 | E | \Biggr ) + m - \sum _ { i } b _ { i } } } \\ { { \displaystyle = 3 h - 3 + m - | \mathbf { b } | . } } \end{array}
$$

Lemma 3.10. ${ \cal I } f \mathfrak { P } _ { h , m }$ holds for all $( h , m ) \prec ( g , n )$ , then $\mathfrak { Q } _ { h , m }$ also holds for all $( h , s ) \prec ( g , n )$

Proof. Recall that $\Omega ^ { [ 0 ] } = R ^ { X } . \Omega ^ { \bf A }$ . This implies that $f _ { h , ( { \bf a } , { \bf b } ) , ( { \bf a } ^ { \prime } , { \bf b } ^ { \prime } ) } ^ { [ 0 ] }$ can be written as a graph sum, where the contribution of a stable graph Γ is given by the following:

• For each ordinary leg $\ell ,$ we insert $R ^ { X } ( - \psi ) ^ { * } \phi _ { a } \psi ^ { b }$ . By Lemma 3.5, this in fact becomes

$$
( \varphi ^ { \bar { a } - m _ { \ell } } , ( - 1 ) ^ { m _ { \ell } } \psi ^ { b + m _ { \ell } } ( R _ { m _ { \ell } } ^ { X } ) ^ { * } \phi _ { a } ) \in \psi ^ { b + m _ { \ell } } \left( \frac { Y } { t ^ { N } } \right) ^ { - \left\lfloor \frac { a } { N } \right\rfloor } \mathbb { Q } [ X ] _ { m _ { \ell } + \left\lfloor \frac { a } { N } \right\rfloor } .
$$

for a unique m (here, note that the ancestor degree must be at most $3 g _ { v } - 3 + n _ { v } < N )$

• For each special leg $\ell ^ { \prime } .$ , we insert $R ^ { X } ( - \psi ) ^ { * } E _ { a ^ { \prime } , b ^ { \prime } } ( \psi )$ . Using Lemma 3.7 and Lemma 3.8, this becomes

$$
\psi ^ { b ^ { \prime \prime } } [ z ^ { b ^ { \prime \prime } } ] ( \varphi ^ { a ^ { \prime \prime } } , R ^ { X } ( - z ) ^ { \ast } E _ { a ^ { \prime } , b ^ { \prime } } ( z ) ) \in \psi ^ { b ^ { \prime \prime } } \bigg ( \frac { Y } { t ^ { N } } \bigg ) ^ { c _ { E _ { \ell ^ { \prime } } } } \mathbb { Q } [ X ] _ { b ^ { \prime \prime } + b ^ { \prime } + 1 }
$$

for a unique $a ^ { \prime \prime } , b ^ { \prime \prime }$

• At every edge, we insert the bivector $V _ { X }$

We now consider the total degree of the contributions from a graph $\Gamma .$

• The total exponent of $\frac { Y } { t ^ { N } }$ is given by

$$
\sum _ { \ell } - \Bigl \lfloor { \frac { a _ { \ell } } { N } } \Bigr \rfloor + \sum _ { \ell ^ { \prime } } c _ { E _ { \ell ^ { \prime } } } + \sum _ { v } ( 1 - g _ { v } ) + \sum _ { e } ( - 1 ) .
$$

Using the fact that

$$
\sum _ { \ell } ( \bar { a } _ { \ell } + b _ { \ell } ) + \sum _ { \ell ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime \prime } + b _ { \ell ^ { \prime } } ^ { \prime \prime } ) = m + n
$$

by Corollary 3.6, we obtain

$$
\begin{array} { l } { { \displaystyle \sum _ { \ell ^ { \prime } } c _ { E _ { \ell ^ { \prime } } } + c + n - \left\lfloor \frac { \mathbf a } { N } \right\rfloor = \sum _ { \ell ^ { \prime } } \frac { a _ { \ell ^ { \prime } } ^ { \prime } + b _ { \ell ^ { \prime } } ^ { \prime } + a _ { \ell ^ { \prime } } ^ { \prime \prime } + b _ { \ell ^ { \prime } } ^ { \prime \prime } - N - 2 } } } \\ { { \displaystyle N } } \\ { { \displaystyle \qquad + \frac { | \mathbf a | + | \mathbf b | - | \mathbf a ^ { \prime } | - | \mathbf b ^ { \prime } | - m + n } { N } + n } } \\ { { \displaystyle \qquad = \frac { \sum _ { \ell ^ { \prime } } ( a _ { \ell ^ { \prime } } ^ { \prime \prime } + b _ { \ell ^ { \prime } } ^ { \prime \prime } ) + | \bar { \mathbf a } | + | \mathbf b | - n N - 2 n - m + n } { N } } } \\ { { \displaystyle } } \\ { { \displaystyle = 0 , } } \end{array}
$$

which implies that the total exponent ${ \mathrm { i s ~ } - \big ( c + n + h - 1 \big ) }$ .

• The total degree in X is at most

$$
\begin{array} { r l } { { } } & { { \displaystyle \sum _ { v } \left( 3 g _ { v } - 3 + n _ { v } - \sum _ { \ell } ( b _ { \ell } + m _ { \ell } ) - \sum _ { \ell ^ { \prime } } b _ { \ell ^ { \prime } } ^ { \prime \prime } - \sum _ { e } m _ { ( e , v ) } \right. } } \\ { { } } & { { \left. + \sum _ { \ell } \left( m _ { \ell } + \left\lfloor \frac { a _ { \ell } } { N } \right\rfloor \right) + \sum _ { \ell ^ { \prime } } ( b _ { \ell ^ { \prime } } ^ { \prime \prime } + b _ { \ell ^ { \prime } } ^ { \prime } + 1 ) \right) + \sum _ { e } \left( m _ { ( e , v _ { 1 } ) } + m _ { ( e , v _ { 2 } ) } + 1 \right) } } \\ { { } } & { { = \displaystyle \left( \sum _ { v } 3 g _ { v } - 3 + n _ { v } \right) - | \mathbf { b } | + | \mathbf { b } ^ { \prime } | + | E | + n + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor } } \\ { { } } & { { = 3 h - 3 + m + 2 n + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor - | \mathbf { b } | + | \mathbf { b } ^ { \prime } | . } } \end{array}
$$

Theorem 3.11. For all $\mathbf { a } , \mathbf { b } \in \{ 0 , \ldots , N + 3 \} ^ { n }$ , we have

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { g - 1 + c } f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 ] } \in \mathbb { Q } [ X ] _ { 3 g - 3 + n + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor - | \mathbf { b } | } .
$$

Proof. We will induct on $( g , n )$ under the ordering ≺. The base case is $( g , n ) = ( 0 , 3 )$ In this case, there is only one graph with a single vertex. Because dim ${ \overline { { \mathcal { M } } } } _ { g , n } = 0 ,$ , no ancestor insertions are allowed, and so we calculate

$$
\begin{array} { c } { { { \displaystyle \left( \frac { Y } { t ^ { N } } \right) } ^ { 0 - 1 + c } f _ { 0 , ( { \bf a } , { \bf 0 } ) } ^ { [ 0 ] } = \left( \frac { Y } { t ^ { N } } \right) ^ { c } I _ { 0 } ^ { 2 } I _ { 1 1 } ^ { 2 } I _ { 2 2 } \frac { t ^ { N } } { Y } \cdot \mathrm { c o n s t } \cdot q ^ { c } } } \\ { { { } } } \\ { { { } = \mathrm { c o n s t } \cdot X ^ { c } . } } \end{array}
$$

Here, we use the fact that $c = \left\lfloor { \frac { \mathbf { a } } { N } } \right\rfloor$ and the computation of genus-zero three-point functions in [Lei24a, §2.4].

We now assume the desired polynomiality result for $( h , m ) \prec ( g , n )$ . This implies $\mathfrak { P } _ { h , m }$ and thus $\mathfrak { Q } _ { h , m }$ for all $( h , m ) \prec ( g , n )$ by Lemma 3.10. We may also assume that $c = \left\lfloor { \frac { \mathbf { a } } { N } } \right\rfloor$ by Corollary 2.16.

We will now consider the [0, 1] theory. By [Lei24a, Theorem 4.1], $f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { [ 0 , 1 ] }$ is a polynomial in q of degree at most $\begin{array} { r } { g - 1 + \frac { 3 g - 3 + | \mathbf { a } | } { N } } \end{array}$ . By Lemma 2.15, this becomes

$$
\begin{array} { c } { g - 1 + \displaystyle \frac { 3 g - 3 + | \mathbf { a } | + n - | \bar { \mathbf { a } } | - | \mathbf { b } | } { N } = g - 1 + \displaystyle \frac { 3 g - 3 + | \mathbf { a } | + n - | \mathbf { a } | - | \mathbf { b } | + N \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor } { N } } \\ { = g - 1 + c + \displaystyle \frac { 3 g - 3 + n - | \mathbf { b } | } { N } . } \end{array}
$$

Because $0 \leq | { \bf b } | \leq 3 g - 3 + n$ and $N \gg 3 g - 3 + n$ , we see that the degree is in fact at most $g - 1 + c$ . Multiplying by $\left( { \frac { Y } { t ^ { N } } } \right) ^ { g - 1 + c }$ , we see that

$$
\left( \frac { Y } { t ^ { N } } \right) ^ { g - 1 + c } f _ { g , ( { \bf a } , { \bf b } ) } ^ { [ 0 , 1 ] } \in \mathbb { Q } [ X ] _ { g - 1 + c } .
$$

By Corollary 2.16, this satisfies the desired degree bound.

We will now apply the bipartite graph decomposition from Theorem 2.7. There is a leading bipartite graph with only a single level 0 vertex. We need to prove the degree estimate for the non-leading graphs. Applying $\mathfrak { Q } _ { h , m }$ at level 0 and Lemma 2.11 at level 1, we now count the total degree contribution of a bipartite graph Λ.

• The total exponent of $\frac { Y } { t ^ { N } }$ is

$$
\begin{array} { r l } & { \quad g - 1 + c - \displaystyle \sum _ { v \in V _ { 0 } } ( g _ { v } - 1 + c _ { v } + | L _ { v } ^ { \prime } | ) - \displaystyle \sum _ { v \in V _ { 1 } } ( g _ { v } - 1 + c _ { v } ) } \\ & { = g - 1 + \displaystyle \frac { | \mathbf { a } | + | \mathbf { b } | - n } { N } } \\ & { \quad - \displaystyle \sum _ { v \in V _ { 0 } } \left( g _ { v } - 1 + \displaystyle \frac { | \mathbf { a } _ { v } | + | \mathbf { b } | _ { n } - | \mathbf { a } _ { v } ^ { \prime } | - | \mathbf { b } _ { v } ^ { \prime } | - | L _ { v } | + | E _ { v } | } { N } + | E _ { v } | \right) } \\ & { \quad - \displaystyle \sum _ { v \in V _ { 1 } } \left( g _ { v } - 1 + \displaystyle \frac { | \mathbf { a } _ { v } | + | \mathbf { b } | _ { n } - | \mathbf { a } _ { v } ^ { \prime } | - | \mathbf { b } _ { v } ^ { \prime } | - | L _ { v } | - | E _ { v } | } { N } \right) } \\ & { = g - 1 + | E | - \displaystyle \sum _ { v \in V } ( g _ { v } - 1 ) } \\ & { = 0 . } \end{array}
$$

• The total degree in X is

$$
\begin{array} { r } { \displaystyle \sum _ { v \in V _ { 0 } } \Big ( 3 g _ { v } - 3 + n _ { v } + | E _ { v } | + \Big \lfloor \frac { \mathbf { a } _ { v } } { N } \Big \rfloor - | \mathbf { b } _ { v } | + | \mathbf { b } _ { v } ^ { \prime } | \Big ) } \\ { + \displaystyle \sum _ { v \in V _ { 1 } } \Big ( 3 g _ { v } - 3 + n _ { v } + \Big \lfloor \frac { \mathbf { a } _ { v } } { N } \Big \rfloor - | \mathbf { b } _ { v } | - | \mathbf { b } _ { v } ^ { \prime } | \Big ) } \end{array}
$$

Because a stable graph describes a codimension $| E |$ stratum in ${ \overline { { \mathcal { M } } } } _ { g , n } ,$ this is at most $\begin{array} { r } { 3 g - 3 + n + \left\lfloor \frac { \mathbf { a } } { N } \right\rfloor - \left. \mathbf { b } \right. } \end{array}$ □

Applying Lemma 3.9, we obtain the following.

Corollary 3.12. For all $( g , n )$ such that $2 g - 2 + n > 0$ , all $\mathbf { a } \in \{ 0 , 1 , 2 , 3 \} ^ { r }$ , and all b $\in \mathbb { Z } _ { \geq 0 } ^ { n } ,$ we have

$$
f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { \mathbf { A } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + n - | \mathbf { b } | } .
$$

3.3. Choice of gauge. Note that

$$
\begin{array} { r } { R ^ { { \bf A } , \mathbb { G } } ( z ) ^ { - 1 } = R ^ { { \bf A } } ( z ) ^ { - 1 } \mathbb { G } ( z ) ^ { - 1 } , } \end{array}
$$

where we compute

$$
\mathbb { G } ( z ) ^ { - 1 } = I - \left( \begin{array} { c c c c } { 0 } & { z c _ { 1 1 } } & { z ^ { 2 } c _ { 2 } } & { - z ^ { 3 } ( c _ { 1 1 } c _ { 2 } + c _ { 3 } ) } \\ & { 0 } & { z c _ { 1 2 } } & { - z ^ { 2 } ( c _ { 1 1 } c _ { 1 2 } + c _ { 2 } ) } \\ & & { 0 } & { c _ { 1 1 } } \\ & & & { 0 } \end{array} \right) .
$$

Note that this is a symplectic matrix, so we have an equality

$$
\Omega ^ { \mathbf { A } , \mathbb { G } } = \mathbb { G } . \Omega ^ { \mathbf { A } }
$$

of $\mathrm { C o h F T s }$

Theorem 3.13. For all $( g , n )$ such that $2 g - 2 + n > 0$ , all $\mathbf { a } \in \{ 0 , 1 , 2 , 3 \} ^ { n }$ , and all b $\in \mathbb { Z } _ { \geq 0 } ^ { n } ,$ we have

$$
f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { \mathbf { A } , \mathbb { G } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + n - | \mathbf { b } | } .
$$

Proof. We will write the stable graph sum formula for $\Omega ^ { \mathbf { A } , \mathbb { G } }$ as the G-action on $\Omega ^ { \mathbf { A } }$ The contribution of a stable graph Γ is given by the following assignments:

• At each leg, we place $\begin{array} { r } { \mathbb { G } ( - z ) ^ { * } \varphi _ { a } \psi ^ { b } = \sum _ { m } \mathbb { G } _ { m } ^ { * } ( - \psi ) ^ { m } \varphi _ { a } \psi ^ { b } ; } \end{array}$

• At each edge, we place

$$
\begin{array} { l } { { \displaystyle V ^ { \mathbb G } : = \sum _ { i = 1 } ^ { 3 } \frac { \varphi _ { i } \otimes \varphi ^ { i } - \mathbb G ( - \psi ) ^ { * } \varphi _ { i } \otimes \mathbb G ( - \psi ^ { \prime } ) ^ { * } \varphi ^ { i } } { \psi + \psi ^ { \prime } } } } \\ { { \displaystyle ~ = Y ^ { - 1 } \sum _ { a , b } V _ { a b } ^ { \mathbb G } \psi ^ { a } ( \psi ^ { \prime } ) ^ { b } . } } \end{array}
$$

Here, note that $\mathbb { G } _ { m } ^ { * }$ has degree m in X and $V _ { a b }$ has degree $a + b + a$ in X by the assumption on the gauge in Definition 1.6.

We now compute the total degree of the contribution. The total exponent of $\frac { Y } { t ^ { N } }$ in the contribution of Γ to $\Omega _ { g , n } ^ { \mathbf { A } , \mathbb { G } }$ is

$$
- | E | - \sum _ { v \in V } ( g _ { v } - 1 ) = - ( g - 1 ) .
$$

On the other hand, the total degree in X is at most

$$
\begin{array} { l } { { \displaystyle \sum _ { v } \Biggl ( 3 g _ { v } - 3 + n _ { v } - \sum _ { \ell \in L _ { v } } ( m _ { \ell } + b _ { \ell } ) - \sum _ { e \in E _ { v } } m _ { ( e , v ) } \Biggr ) } } \\ { { \displaystyle \qquad + \sum _ { e } ( m _ { ( e , v _ { 1 } ) } + m _ { ( e , v _ { 2 } ) } + 1 ) + \sum _ { \ell } m _ { \ell } } } \\ { { \displaystyle = 3 g - 3 + n - | { \bf b } | . } } \end{array}
$$

## 4. The B-model Feynman rule

In this section, we will define the B-model Feynman rule and prove that it equals the A-model Feynman rule. From now on, we will make the specialization $t ^ { N } = - 1$ This makes $q ^ { \prime } = q$ and makes

$$
f _ { g , ( \mathbf { a } , \mathbf { b } ) } ^ { \mathbf { A } , \mathbb { G } } = ( p _ { k } Y ) ^ { g - 1 } \int _ { \overline { { \mathcal { M } } } _ { g , n } } \Omega _ { g , n } ^ { \mathbf { A } , \mathbb { G } } ( \varphi _ { a _ { 1 } } \psi _ { 1 } ^ { b _ { 1 } } , \dots , \varphi _ { a _ { n } } \psi _ { n } ^ { b _ { n } } ) \mathrm { . }
$$

Convention 4.1. In this section, we will omit all superscripts of $\mathbb { G }$ , so $E _ { * }$ <sub>∗</sub> stands for $E _ { * * } ^ { \mathbb { G } } , R ^ { \mathbf { A } }$ stands for $R ^ { \mathbf { A } , \mathbb { G } }$ , and so on.

4.1. B-model geometric quantization. We will first express the physics Feynman rule using geometric quantization. Note that the Givental formalism is a type of geometric quantization, so we will be able to compare the A-model and B-model quantizations.

Consider the vector space

$$
\begin{array} { r } { \mathcal { H } _ { S } : = T ^ { * } ( z H ^ { 0 } ( Z ) \oplus H ^ { 2 } ( Z ) ) = \mathrm { s p a n } \{ - \varphi _ { 2 } z ^ { - 1 } , \varphi _ { 3 } z ^ { - 2 } , \varphi _ { 1 } , \varphi _ { 0 } z \} } \end{array}
$$

with the symplectic form

$$
{ \frac { 1 } { p _ { k } Y } } \operatorname { R e s } _ { z = 0 } ( f ( - z ) , g ( z ) ) = { \binom { 0 } { - I } } ~ 0 \biggr ) .
$$

Then define

$$
\begin{array} { r l } & { { \cal R } ^ { \mathbf { B } } : = { \cal R } ^ { \mathbf { A } } | _ { \mathcal { H } _ { S } } } \\ & { \quad = \left( \begin{array} { c c c } { 1 } & { - { \cal E } _ { \psi } } & { } \\ { 0 } & { 1 } & { } \\ { - { \cal E } _ { \varphi \varphi } } & { - { \cal E } _ { \varphi \psi } } & { 1 } \\ { { \cal E } _ { 1 \varphi \psi } } & { { \cal E } _ { 1 \psi ^ { 2 } } } & { { \cal E } _ { \psi } } & { 1 } \end{array} \right) } \\ & { \quad \quad = : \left( \begin{array} { c c } { A } & { B } \\ { C } & { D } \end{array} \right) . } \end{array}
$$

Because $\mathcal { H } _ { S }$ is a symplectic vector space, we will write elements as

$$
( \mathbf { p } , \mathbf { x } ) : = - p _ { x } \varphi _ { 2 } z ^ { - 1 } + p _ { y } \varphi _ { 3 } z ^ { - 2 } + x \varphi _ { 1 } + y \varphi _ { 0 } z .
$$

Definition 4.2. Following [CPS18], we define the geometric quantization $\widehat { R } ^ { \mathbf { B } }$ by the Gaussian integral

$$
\widehat { R } ^ { \mathbf { B } } F ( \hbar , \mathbf { x } ) : = \log \int _ { \mathbb { R } ^ { 4 } } e ^ { \frac { 1 } { \hbar } ( \mathbf { Q } ( \mathbf { x } ^ { \prime } , \mathbf { p } ^ { \prime } ) - \mathbf { x } ^ { \prime } \cdot \mathbf { p } ^ { \prime } ) + F ( \hbar , \mathbf { x } ^ { \prime } ) } \mathrm { d } \mathbf { x } ^ { \prime } \mathrm { d } \mathbf { p } ^ { \prime } .
$$

Here, $\mathbf { Q } ( \mathbf { x } ^ { \prime } , \mathbf { p } ^ { \prime } )$ is defined by the formula

$$
\begin{array} { r l } & { \mathbf { Q } ( \mathbf { x } ^ { \prime } , \mathbf { p } ^ { \prime } ) : = ( D ^ { - 1 } \mathbf { x } ^ { \prime } ) \cdot \mathbf { p } ^ { \prime } - \frac { 1 } { 2 } ( D ^ { - 1 } C \mathbf { p } ^ { \prime } ) \cdot \mathbf { p } ^ { \prime } } \\ & { \qquad = ( \mathbf { p } ^ { \prime } ) ^ { T } \left( \begin{array} { l l } { 1 } & { } \\ { - E _ { \psi } } & { 1 } \end{array} \right) \mathbf { x } ^ { \prime } + \frac { 1 } { 2 } ( \mathbf { p } ^ { \prime } ) ^ { T } \left( \begin{array} { l l } { E _ { \varphi \varphi } } & { E _ { \varphi \psi } } \\ { E _ { \varphi \psi } } & { E _ { \psi \psi } } \end{array} \right) \mathbf { p } ^ { \prime } } \end{array}
$$

and $( \mathbf { p } ^ { \prime } , \mathbf { x } ^ { \prime } )$ are coordinates on $\mathbb { R } ^ { 4 } = \mathbb { R } ^ { 2 } \times \mathbb { R } ^ { 2 }$

Following [CPS18, §3.4], a standard argument involving the Fourier transform gives us the operator form

$$
\begin{array} { r } { \widehat { R } ^ { { \bf B } } F ( \hbar , { \bf x } ) = \log \left( e ^ { - \frac { \hbar } { 2 } ( \partial _ { x } \ \partial _ { y } ) D C ^ { T } \left( \frac { \partial _ { x } } { \partial _ { y } } \right) } e ^ { F ( \hbar , D ^ { - 1 } { \bf x } ) } \right) . } \end{array}
$$

Now define $\tilde { E } _ { \varphi \varphi } , \tilde { E } _ { \varphi \psi }$ , and ${ \tilde { E } } _ { \psi \psi }$ by

$$
- D C ^ { T } : = \left( { \begin{array} { l l } { \tilde { E } _ { \varphi \varphi } } & { \tilde { E } _ { \varphi \psi } } \\ { \tilde { E } _ { \varphi \psi } } & { \tilde { E } _ { \psi \psi } } \end{array} } \right) .
$$

Then if we define

$$
V ^ { \mathbf { B } } ( \partial _ { \mathbf x } , \partial _ { \mathbf x } ) : = \frac { 1 } { 2 } \tilde { E } _ { \varphi \varphi } \frac { \partial ^ { 2 } } { \partial x ^ { 2 } } + \tilde { E } _ { \varphi \psi } \frac { \partial ^ { 2 } } { \partial x \partial y } + \frac { 1 } { 2 } \tilde { E } _ { \psi \psi } \frac { \partial ^ { 2 } } { \partial y ^ { 2 } } ,
$$

the operator form of the quantization action becomes

$$
\widehat { R } ^ { \mathbf { B } } F ( \hbar , \mathbf { x } ) = \log \Big ( e ^ { \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { x } } , \partial _ { \mathbf { x } } ) } e ^ { F ( \hbar , D ^ { - 1 } \mathbf { x } ) } \Big ) .\tag{4.1}
$$

Definition 4.3. Define the (normalized) Gromov-Witten correlator of $Z$ by the formula

$$
P _ { g , m , n } : = \frac { ( p _ { k } Y ) ^ { g - 1 } } { I _ { 0 } ^ { 2 g - 2 + m + n } } \big < \varphi _ { 1 } ^ { \otimes m } , ( \varphi _ { 0 } \psi ) ^ { \otimes n } \big > _ { g , m + n } ^ { Z }
$$

when $( g , m ) \neq ( 1 , 0 )$ and define

$$
P _ { 1 , 0 , n } : = ( n - 1 ) ! \biggl ( \frac { \chi ( Z ) } { 2 4 } - 1 \biggr ) .
$$

Definition 4.4. Define the master B-model Gromov-Witten potential function by

$$
P ^ { \mathbf { B } } ( \hbar , x , y ) : = \sum _ { g , m , n } \hbar ^ { g - 1 } \frac { x ^ { m } y ^ { n } } { m ! n ! } P _ { g , m , n } .
$$

Then, define the master B-model potential function by

$$
f ^ { \mathbf { B } } ( h , x , y ) : = \widehat { R } ^ { \mathbf { B } } P ^ { \mathbf { B } } ( h , x , y ) = : \sum _ { g , m , n } \ : h ^ { g - 1 } f _ { g , m , n } ^ { \mathbf { B } } .
$$

By [CPS18, Theorem 10], we can also compute $f ^ { \mathbf { B } }$ by the construction in Definition 1.8.

4.2. Factorization of the quantization action. We will factor the quantization action (4.1) into the change of variables and the application of diferential operators. Observe that $D ^ { - 1 } \mathbf { x } = ( x , y - E _ { \psi } x )$ . Then the transformation

$$
F ( \hbar , x , y ) \mapsto F ( \hbar , x , y - E _ { \psi } x )
$$

is given by quantizing the matrix

$$
\begin{array} { r } { \boldsymbol { \mathcal { E } ^ { \mathbf { B } } } : = \left( \begin{array} { c c c c } { 1 } & { - E _ { \psi } } & & \\ & { 1 } & & \\ & & { 1 } & \\ & & & { E _ { \psi } } & { 1 } \end{array} \right) . } \end{array}
$$

Then we compute

$$
\begin{array} { r l } {  { \tilde { P } ^ { \mathbf { B } } : = \widehat { \mathcal { E } } ^ { \mathbf { B } } P ^ { \mathbf { B } } ( \hbar , x , y ) } } \\ & { = P ^ { \mathbf { B } } ( \hbar , x , y - E _ { \psi } x ) } \\ & { = \displaystyle \sum _ { g , m , n } \hbar ^ { g - 1 } \frac { x ^ { m } y ^ { n } } { m ! n ! } \tilde { P } _ { g , m , n } , } \end{array}
$$

where

$$
\tilde { P } _ { g , m , n } : = \frac { ( p _ { k } Y ) ^ { g - 1 } } { I _ { 0 } ^ { 2 g - 2 + m + n } } \big \langle ( \varphi _ { 1 } - E _ { \psi } \varphi _ { 0 } \psi ) ^ { \otimes m } , ( \varphi _ { 0 } \psi ) ^ { \otimes n } \big \rangle _ { g , m + n } ^ { Z } .
$$

We then compute

$$
\tilde { R } ^ { \mathbf { B } } : = R ^ { \mathbf { B } } ( \mathcal { E } ^ { \mathbf { B } } ) ^ { - 1 } = \left( \begin{array} { c c c c } { 1 } & { 0 } & { } & { } \\ { 0 } & { 1 } & { } & { } \\ { - \tilde { E } _ { \varphi \varphi } } & { - \tilde { E } _ { \varphi \psi } } & { 1 } & { } \\ { - \tilde { E } _ { \varphi \psi } } & { - \tilde { E } _ { \psi \psi } } & { 0 } & { 1 } \end{array} \right) ,
$$

so we see that $f ^ { \mathbf { B } } ( \hbar , x , y ) = \widehat { \tilde { R } ^ { \mathbf { B } } \tilde { P } ^ { \mathbf { B } } } ( \hbar , x , y )$

4.3. Modification of the A-model quantization. Note that in the graph sum formula for $\Omega ^ { \mathbf { A } }$ , the edge contribution is given by

$$
\begin{array} { r l } & { V _ { \mathbf { A } } = V _ { \mathbf { B } } + E _ { \psi } ( \varphi _ { 0 } \otimes \varphi _ { 2 } + \varphi _ { 2 } \otimes \varphi _ { 0 } ) + E _ { 1 \varphi \psi } ( \varphi _ { 0 } \otimes \varphi _ { 1 } \psi ^ { \prime } + \varphi _ { 1 } \psi \otimes \varphi _ { 0 } ) } \\ & { \qquad + E _ { 1 \psi ^ { 2 } } ( \varphi _ { 0 } \otimes \varphi _ { 0 } ( \psi ^ { \prime } ) ^ { 2 } + \varphi _ { 0 } \psi ^ { 2 } \otimes \varphi _ { 0 } ) . } \end{array}
$$

In order to prove that the A-model and B-model Feynman rules are equivalent, we need to analyze the contributions of the three extra terms. We will begin with the terms $E _ { \psi } ( \varphi _ { 0 } \otimes \varphi _ { 2 } + \varphi _ { 2 } \otimes \varphi _ { 0 } )$ and study a parallel construction to the modified B-model quantization.

The parallel construction in the A-model is to consider the matrix<sup>7</sup>

$$
\mathcal { E } ^ { \mathbf { A } } : = I + z \left( \begin{array} { c c c c } { 0 } & { E _ { \psi } } & & \\ & { 0 } & & \\ & & { 0 } & { E _ { \psi } } \\ & & & { 0 } \end{array} \right)
$$

and the factorization

$$
\tilde { R } ^ { \mathbf { A } } ( z ) : = R ^ { \mathbf { A } } ( z ) \mathcal { E } ^ { \mathbf { A } } ( z ) ^ { - 1 } .
$$

Recall that matrices are written in the basis $\varphi _ { 0 } , \varphi _ { 1 } , \varphi _ { 2 } , \varphi _ { 3 }$

Definition 4.5. Define the CohFT

$$
\begin{array} { r } { \tilde { \Omega } ^ { Z } : = \mathcal { E } ^ { \mathbf { A } } \Omega ^ { Z } } \end{array}
$$

and the potential

$$
\tilde { P } ^ { \mathbf { A } } ( \hbar , \mathbf { t } ) : = \sum _ { g , n } \frac { \hbar ^ { g - 1 } } { n ! } ( p _ { k } Y ) ^ { g - 1 } \int _ { \overline { { \mathcal { M } } } _ { g , n } } \tilde { \Omega } _ { g , n } ^ { Z } ( \mathbf { t } ^ { \otimes n } )
$$

for the coordinate

$$
\mathbf { t } = x \varphi _ { 1 } + y \varphi _ { 0 } \psi + a \varphi _ { 1 } \psi + b \varphi _ { 0 } \psi ^ { 2 } + c \varphi _ { 0 } .
$$

Specializing to the case $\mathbf { t } = ( \mathbf { x } , 0 )$ , we define

$$
\tilde { P } ^ { \mathbf { A } } ( \hbar , x , y ) : = \tilde { P } ^ { \mathbf { A } } ( \hbar , x \varphi _ { 0 } + y \varphi _ { 0 } \psi ) .
$$

Lemma 4.6. We have the identity

$$
\tilde { P } ^ { \bf A } ( h , x , y ) = \tilde { P } ^ { \bf B } ( h , x , y ) - \log ( 1 - y ) .
$$

Proof. By [Lee09, Theorem $5 ] .$ , the R-matrix action preserves all tautological equations on the moduli spaces of curves, in particular the string and dilaton equations, so we can apply the dilaton equation to $\bar { \Omega } ^ { Z }$ . We also note that changing $\tilde { P } ^ { \tilde { \mathbf { B } } } ( \hbar , x , y )$ to $\tilde { P } ^ { \mathbf { B } } ( \hbar , x , y )$ is the same as replacing $P _ { 1 , 0 , n }$ by the actual Gromov-Witten invariant

$$
\frac { 1 } { I _ { 0 } ^ { n } } \big \langle ( \varphi _ { 0 } \psi ) ^ { \otimes n } \big \rangle _ { 1 , n } ^ { Z } = ( n - 1 ) ! \frac { \chi ( Z ) } { 2 4 } ,
$$

so applying the dilaton equation to both sides (where $\tilde { P }$ denotes either $\tilde { P } ^ { \mathbf { A } } \ \mathrm { o r } \ \tilde { P } ^ { \mathbf { B } } )$ yields

$$
\begin{array} { l } { \displaystyle \frac { \partial } { \partial y } \tilde { P } ( \hbar , x , y ) = \frac { \partial } { \partial y } \left( \underset { ( g , m , n ) \neq ( 1 , 0 , 1 ) } { \sum } \hbar ^ { g - 1 } \frac { x ^ { m } y ^ { n } } { m ! n ! } \tilde { P } _ { g , m , n } + \frac { \chi ( Z ) } { 2 4 } y \right) } \\ { = \underset { g , m , n } { \sum } \hbar ^ { g - 1 } \frac { x ^ { m } y ^ { n - 1 } } { m ! ( n - 1 ) ! } \tilde { P } _ { g , m , n } + \frac { \chi ( Z ) } { 2 4 } } \\ { = \underset { g , m , n } { \sum } \hbar ^ { g - 1 } \frac { x ^ { m } y ^ { n - 1 } } { m ! ( n - 1 ) ! } ( 2 g - 2 + m + n - 1 ) \tilde { P } _ { g , m , n - 1 } + \frac { \chi ( Z ) } { 2 4 } } \\ { = \left( 2 \hbar \frac { \partial } { \partial \hbar } + x \frac { \partial } { \partial x } + y \frac { \partial } { \partial y } \right) \tilde { P } + \frac { \chi ( Z ) } { 2 4 } . } \end{array}
$$

Therefore, we only need to prove that $\tilde { P } ^ { \mathbf { A } } ( \hbar , x , 0 ) = \tilde { P } ^ { \mathbf { B } } ( \hbar , x , 0 )$

We will now consider the graph sum formula for the definition of $\tilde { \Omega } ^ { Z }$ . The edge contributions are given by $E _ { \psi } ( \varphi _ { 0 } \otimes \varphi _ { 2 } + \varphi _ { 2 } \otimes \varphi _ { 0 } )$ . All insertions at legs are $\mathfrak { E } ^ { \mathbf { A } } ( - \psi ) ^ { * } \varphi _ { 1 } = \varphi _ { 1 } - E _ { \psi } \varphi _ { 0 } \psi$ , and each vertex contributes a Gromov-Witten correlator of $Z .$ . Applying the string equation, dilaton equation, divisor equation, and virtual dimension constraints, if the stable graph Γ has at least one edge and one vertex of $g > 0$ , then its contribution vanishes. By a similar argument, any vertex with more than two edges has vanishing contribution. Therefore, we have a decomposition

$$
\tilde { P } ^ { \mathbf { A } } ( \hbar , x , 0 ) = P ^ { \mathbf { A } } ( \hbar , x , - E _ { \psi } x ) + P _ { 1 } ^ { \mathsf { l o o p } } ( x ) ,
$$

where the first term comes from the leading graphs with a single genus $g$ vertex and the second comes from loops of genus zero vertices, which contribute to the genus 1 potential. Every vertex must have at least one $\varphi _ { 1 }$ insertion by dimension reasons, and the string and dilaton equations imply that there is exactly one $\varphi _ { 1 }$ insertion. Therefore, we use the dilaton equation to remove the $- E _ { \psi } \varphi _ { 0 } \psi$ insertions and compute

$$
\begin{array} { r l } { P _ { 1 } ^ { \mathrm { l o o p } } ( x ) = } & { \displaystyle \sum _ { \stackrel { \mathrm { r } \in \mathrm { l o o p ~ } } { \mathrm { r } \in \mathrm { I } } } \frac { x ^ { m + n } } { m ! n ! } \frac { \mathrm { C o n t } \Gamma } { | \mathrm { A u t } \Gamma | } } \\ & { ~ | \displaystyle \sum _ { | L | = m + n } ^ { | \mathrm { r } | \mathrm { l o o p } } } \\ & { = \displaystyle \sum _ { m > 0 } \frac { ( m - 1 ) ! } { m ! } ( E _ { \psi \psi } x ) ^ { m } \displaystyle \prod _ { i = 1 } ^ { m } \sum _ { n _ { i } \geq 0 } ( - E _ { \psi } x ) ^ { n _ { i } } } \\ & { = \displaystyle \sum _ { m > 0 } \frac { 1 } { m } \bigg ( \frac { E _ { \psi } x } { 1 + E _ { \psi } x } \bigg ) ^ { m } } \\ & { = - \log \bigg ( 1 - \frac { E _ { \psi } x } { 1 + E _ { \psi } x } \bigg ) } \\ & { = | \mathrm { o g } ( 1 + E _ { \psi } x ) . } \end{array}
$$

Here, we have used the following combinatorial facts:

• There are $( m - 1 ) !$ ways to arrange m vertices in a loop;

• For any partition $n = n _ { 1 } + \cdot \cdot \cdot + n _ { m }$ of the $\varphi _ { 0 } \psi$ insertions, the number of possible assignments is ${ \frac { n ! } { n _ { 1 } ! \cdots n _ { m } ! } } ;$

• Applying the dilaton equation to any vertex with $n _ { i }$ insertions of $\varphi _ { 0 } \psi$ and one insertion of $\varphi _ { 1 }$ produces a factor of n!.

We conclude that

$$
\begin{array} { r l } & { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , 0 ) = P ^ { \mathbf { A } } ( \hbar , x , - E _ { \psi } x ) + \log ( 1 + E _ { \psi } x ) } \\ & { \quad \quad \quad = P ^ { \mathbf { B } } ( \hbar , x , - E _ { \psi } x ) } \\ & { \quad \quad \quad = \tilde { P } ^ { \mathbf { B } } ( \hbar , x , 0 ) . } \end{array}
$$

4.4. Equality of A-model and B-model potentials. A direct computation yields

$$
\tilde { R } ^ { \mathbf { A } } ( z ) ^ { - 1 } = I - \left( \begin{array} { c c c c } { 0 } & { 0 } & { z ^ { 2 } \tilde { E } _ { \varphi \psi } } & { z ^ { 3 } \tilde { E } _ { \psi \psi } } \\ { 0 } & { z \tilde { E } _ { \varphi \varphi } } & { z ^ { 2 } \tilde { E } _ { \varphi \psi } } \\ { 0 } & { 0 } & { 0 } \\ { } & { } & { 0 } \end{array} \right) .
$$

By [Giv01, Proposition 7.3], we see that

$$
e ^ { f ^ { \mathbf { A } } ( \hbar , x , y ) } = e ^ { \hbar V ^ { \mathbf { A } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y ) } ,
$$

where

$$
\begin{array} { c } { { \displaystyle { V ^ { \mathbf { A } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) : = V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) - \tilde { E } _ { \varphi \psi } \frac { \partial ^ { 2 } } { \partial a \partial c } - \tilde { E } _ { \psi \psi } \frac { \partial ^ { 2 } } { \partial b \partial c } } } } \\ { { \displaystyle { = : V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) + V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) . } } } \end{array}
$$

We will first prove some technical lemmas about the geometric quantization formalism. This is

Lemma 4.7. We have the equality

$$
e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y , a , b , c ) } = e ^ { \frac { c } { 1 - y } \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \right) } e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y ) } .
$$

Proof. The operator form of the string equation $^ { 1 ^ { 8 } }$ is

$$
\frac { \partial } { \partial c } e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y , a , b , c ) } = \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } + y \frac { \partial } { \partial v } \right) e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y , a , b , c ) } .
$$

By virtual dimension reasons, we obtain the initial condition

$$
\begin{array} { r } { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y , a , b , 0 ) = \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y ) . } \end{array}
$$

The desired result follows from the computation

$$
\begin{array} { r l } & { ( 1 - y ) \displaystyle \frac { \partial } { \partial c } \Big ( e ^ { \frac { c } { 1 - y } \big ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \big ) } e ^ { \tilde { P } ^ { \mathbf { A } } ( h , x , y ) } \Big ) } \\ & { \quad \quad \quad = ( 1 - y ) \displaystyle \frac { \partial } { \partial c } \sum _ { n = 0 } ^ { \infty } \frac { 1 } { n ! } \bigg ( \frac { c } { 1 - y } \bigg ) ^ { n } \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) ^ { n } e ^ { \tilde { P } ( h , x , y ) } } \\ & { \quad \quad \quad = \displaystyle \sum _ { n = 0 } ^ { \infty } \frac { 1 } { ( n - 1 ) ! } \bigg ( \frac { c } { 1 - y } \bigg ) ^ { n - 1 } \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) ^ { n } e ^ { \tilde { P } ^ { \mathbf { A } } ( h , x , y ) } } \\ & { \quad \quad \quad = \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) \Big ( e ^ { \frac { c } { 1 - y } \big ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \big ) } e ^ { \tilde { P } ^ { \mathbf { A } } ( h , x , y ) } \bigg ) . } \end{array}
$$

Theorem 4.8. We have the equality

$$
f ^ { \mathbf { A } } ( \hbar , x , y ) = f ^ { \mathbf { B } } ( \hbar , x , y ) - \log ( 1 - y ) .
$$

Proof. Our goal is to compute the function

$$
\begin{array} { l } { { e ^ { \int ^ { \mathbf { A } } ( \hbar , x , y ) } = e ^ { \hbar ( V ^ { \mathbf { B } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) + V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) ) } e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y , a , b , c ) } \bigg | _ { a , b , c = 0 } } } \\ { { = e ^ { \hbar ( V ^ { \mathbf { B } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) + V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) ) } e ^ { \frac { c } { 1 - y } \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \right) } e ^ { \tilde { P } ^ { \mathbf { A } } ( \hbar , x , y ) } \bigg | _ { a , b , c = 0 } } } \\ { { = e ^ { \hbar ( V ^ { \mathbf { B } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) + V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf t } , \partial _ { \mathbf t } ) ) } e ^ { \frac { c } { 1 - y } \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \right) } \frac { e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } } { 1 - y } \bigg | _ { a , b , c = 0 } . } } \end{array}
$$

We will first consider the contribution of $\begin{array} { r } { \frac { c } { 1 - y } \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \right) } \end{array}$ and $V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } )$ . For any function $\mathcal { D } ( x , y )$ , we compute

$$
\begin{array} { r l } & { e ^ { \hbar b ^ { \prime } \cdots \nu ^ { ( a _ { k } , \mathfrak { s } ) } ( \tilde { a } _ { * } , \mathfrak { s } _ { k } ) } e ^ { - \frac { c } { 1 - \nu } \left( a _ { \mathfrak { s } ^ { \dagger } } ^ { \partial } + b _ { \mathfrak { s } ^ { \dagger } } ^ { \partial } \right) } \mathbb { D } ( x , y ) } \\ & { = \displaystyle \sum _ { m , n } \frac { ( - \hbar ) ^ { m } } { m ! n ! } \bigg ( \tilde { E } _ { \varphi \varphi } \frac { \partial ^ { 2 } } { \partial a \partial c } + \tilde { E } _ { \psi \psi } \frac { \partial ^ { 2 } } { \partial b \partial \mathcal { c } } \bigg ) ^ { m ^ { 2 } } \bigg ( \frac { c } { 1 - y } \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) \bigg ) ^ { n } \mathbb { D } ( x , y | _ { a , b , c = 0 } } \\ & { = \displaystyle \sum _ { n } \frac { ( - \hbar ) ^ { n } } { ( n ! ) ^ { 2 } } \bigg ( \tilde { E } _ { \varphi \varphi } \frac { \partial ^ { 2 } } { \partial a \partial c } + \tilde { E } _ { \psi \psi } \frac { \partial ^ { 2 } } { \partial b \partial \mathcal { c } } \bigg ) ^ { n } \bigg ( \frac { c } { 1 - y } \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) \bigg ) ^ { n } \mathbb { D } ( x , y | _ { a , b , c = 0 } } \\ & { = \displaystyle \sum _ { n } \frac { ( - \hbar ) ^ { m } } { n ! } \bigg ( \tilde { E } _ { \varphi \varphi } \frac { \partial } { \partial a } + \tilde { E } _ { \psi \psi } \frac { \partial } { \partial b } \bigg ) ^ { n } \bigg ( \frac { 1 } { 1 - y } \bigg ( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \bigg ) \bigg ) ^ { n } \mathbb { D } ( x , y | _ { a , b , c = 0 } } \\ &  = \displaystyle \sum _ { n } \bigg ( \frac  ( - \hbar  \end{array}
$$

Now set $\begin{array} { r } { E ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } ) : = \frac { - \hbar } { 1 - y } \Big ( \tilde { E } _ { \varphi \psi } \frac { \partial } { \partial x } + \tilde { E } _ { \psi \psi } \frac { \partial } { \partial y } \Big ) } \end{array}$

To deal with the contribution of $V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } )$ , we compute

$$
\begin{array} { r l } & { e ^ { - \hbar V ^ { \mathbf { B } } ( \tilde { g } _ { \mathrm { t } } , \partial _ { \mathbf { t } } ) } ( 1 - y ) e ^ { \hbar V ^ { \mathbf { B } } ( \tilde { g } _ { \mathrm { t } } , \partial _ { \mathbf { t } } ) } } \\ & { \qquad = \left( \underset { m \leq 0 } { \sum } \frac { ( - \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ) ^ { m } } { m ! } \right) ( 1 - y ) \left( \underset { n \geq 0 } { \sum } \frac { ( - \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ) ^ { n } } { n ! } \right) } \\ & { \qquad = \underset { n \geq 0 \neq i \mathrm { m } = \mathrm { m } } { \sum } \frac { ( - \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ) ^ { \ell } } { \ell ! } ( 1 - y ) \frac { ( \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ) ^ { m } } { m ! } } \\ & { \qquad = \underset { n \geq 0 } { \sum } \frac { 1 } { n ! } ( [ - , V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ] ) ^ { n } ( 1 - y ) } \\ & { \qquad = ( 1 - y ) + \hbar \Big ( \tilde { E } _ { \varphi \psi } \frac { \partial } { \partial x } + \tilde { F } _ { \psi \psi } \frac { \partial } { \partial y } \Big ) . } \end{array}
$$

Dividing by $1 - y$ , we see that

$$
( 1 - y ) ^ { - 1 } e ^ { - \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } ( 1 - y ) e ^ { \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } = 1 - E ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } ) ,
$$

or in other words that

$$
e ^ { - \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } ( 1 - y ) ^ { - 1 } e ^ { \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } ( 1 - y ) = \sum _ { n \geq 0 } { E } ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } ) ^ { n } .
$$

Putting all of this together, we see that

$$
\begin{array} { l } { { \displaystyle e ^ { f ^ { \mathbf { A } } ( \hbar , x , y ) } = e ^ { \hbar ( V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) + V ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) ) } e ^ { \frac { c } { 1 - y } \left( a \frac { \partial } { \partial x } + b \frac { \partial } { \partial y } \right) } \frac { e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } } { 1 - y } \Bigg \vert _ { a , b , c = 0 } } } \\ { { \displaystyle ~ = e ^ { \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } \sum _ { n \geq 0 } E ^ { \mathrm { e x t r a } } ( \partial _ { \mathbf { t } } ) ^ { n } ( 1 - y ) ^ { - 1 } e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } } } \\ { { \displaystyle ~ = ( 1 - y ) ^ { - 1 } e ^ { \hbar V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } } } \\ { { \displaystyle ~ = \frac { e ^ { f ^ { \mathbf { B } } ( \hbar , x , y ) } } { 1 - y } . } } \end{array}
$$

The desired result follows by taking logarithms.

Corollary 4.9 (B-model Feynman rule). For any $g , m , n ,$ we have

$$
f _ { g , m , n } ^ { \mathbf { B } } \in \mathbb { Q } [ X ] _ { 3 g - 3 + m } .
$$

Proof. By Theorem 4.8, we see that $f _ { g , m , n } ^ { \mathbf { A } } = f _ { g , m , n } ^ { \mathbf { B } } + \delta _ { g , 1 } \delta _ { m , 0 } ( n - 1 ) !$ . The result then follows from Corollary 3.12 by choosing $\mathbf { a } = \left( 1 ^ { m } 0 ^ { n } \right)$ and $\mathbf { b } = \left( 0 ^ { n } 1 ^ { m } \right)$ □

## 5. Anomaly equations

Our goal is to prove the following theorem.

Theorem 5.1. The $P _ { g , m }$ satisfy the diferential equations

(5.1)

$$
- \partial _ { A } P _ { g } = \frac { 1 } { 2 } \Biggl ( P _ { g - 1 , 2 } + \sum _ { g _ { 1 } + g _ { 2 } = g } P _ { g _ { 1 } , 1 } P _ { g _ { 2 } , 2 } \Biggr ) ,\tag{5.2}
$$

$$
( - 2 \partial _ { A } + \partial _ { B } + ( A + 2 B ) \partial _ { B _ { 2 } } - ( ( B - X ) ( A + 2 B ) - B _ { 2 } - r _ { 0 } X ) \partial _ { B _ { 3 } } ) P _ { g } = 0 .
$$

In order to prove this, we introduce a smaller ring of modified generators which contains the $P _ { g }$

Definition 5.2. Define the modified generators

$$
\begin{array} { r } { \mathcal { E } _ { 1 } : = \tilde { E } _ { \varphi \varphi } , \qquad \mathcal { E } _ { 2 } : = \tilde { E } _ { \varphi \psi } , \qquad \mathcal { E } _ { 3 } : = \tilde { E } _ { \psi \psi } } \end{array}
$$

and then set

$$
\tilde { \mathcal { R } } : = \mathbb { Q } [ \mathcal { E } _ { 1 } , \mathcal { E } _ { 2 } , \mathcal { E } _ { 3 } , X ] \subset \mathcal { R } .
$$

Remark 5.3. The ring $\tilde { \mathcal { R } }$ is in fact invariant under the choice of gauge. Direct computation yields

$$
\begin{array} { r l } & { \mathcal { E } _ { 1 } ^ { \mathbb { G } } = \mathcal { E } _ { 1 } ^ { \mathbf { 0 } } + c _ { 1 2 } , } \\ & { \mathcal { E } _ { 2 } ^ { \mathbb { G } } = \mathcal { E } _ { 2 } ^ { \mathbf { 0 } } + c _ { 1 1 } \mathcal { E } _ { 1 } ^ { \mathbf { 0 } } + c _ { 1 1 } c _ { 1 2 } + c _ { 2 } , } \\ & { \mathcal { E } _ { 3 } ^ { \mathbb { G } } = \mathcal { E } _ { 3 } ^ { \mathbf { 0 } } + 2 c _ { 1 1 } \mathcal { E } _ { 2 } ^ { \mathbf { 0 } } + c _ { 1 1 } ^ { 2 } \mathcal { E } _ { 1 } ^ { \mathbf { 0 } } + c _ { 1 1 } ^ { 2 } c _ { 1 2 } + 2 c _ { 1 1 } c _ { 2 } + c _ { 3 } , } \end{array}
$$

so we will write the generators with no superscript and $\mathbb { G } = \mathbf { 0 }$ . Here, recall that $c _ { 1 1 } , c _ { 1 2 } , c _ { 2 } , c _ { 3 } \in \mathbb { Q } [ X ]$

Remark 5.4. Our generators are related to the generators $v _ { 1 } , v _ { 2 }$ , and $v _ { 3 }$ introduced in [YY04] by the formulae

$$
v _ { 1 } = - \pounds _ { 1 } , \qquad v _ { 2 } = - \pounds _ { 2 } , \qquad \mathrm { a n d } \qquad v _ { 3 } = \pounds _ { 3 } - \pounds _ { 2 } X .
$$

Lemma 5.5. The ring $\tilde { \mathcal { R } }$ is closed under the derivative $D$

Proof. A direct computation yields

$$
\begin{array} { l } { D \mathscr { E } _ { 1 } = - X ( \mathscr { E } _ { 1 } + r _ { 0 } ) - \mathscr { E } _ { 1 } ^ { 2 } + 2 \mathscr { E } _ { 2 } , } \\ { D \mathscr { E } _ { 2 } = - X \mathscr { E } _ { 2 } - \mathscr { E } _ { 1 } \mathscr { E } _ { 2 } + \mathscr { E } _ { 3 } , } \\ { D \mathscr { E } _ { 3 } = r _ { 1 } X - X \mathscr { E } _ { 3 } - \mathscr { E } _ { 2 } ^ { 2 } . } \end{array}
$$

Theorem 5.6 (Reduction of generators). Let $g > 1$ . Then $P _ { g } \in \tilde { \mathcal { R } }$

Proof. First, note that by definition, we have $P _ { g } = \tilde { P } _ { g }$ . We will now prove that all $\tilde { P } _ { g , m } \in \tilde { \mathcal { R } }$ by induction on the lexicographic order in $( g , m )$ ). Recall that $f _ { g , m } ^ { \mathbf { B } }$ can be computed from $\tilde { P } _ { h \leq g , m , n } ^ { \mathbf { B } }$ by the geometric quantization of $\mathcal { R } ^ { \mathbf { B } }$ . The contribution of each stable graph to this quantization is given by the following construction:

• At each leg, we place $\varphi _ { 1 }$ or φ<sub>0</sub>ψ;

• At every edge, we place the bivector

$$
\begin{array} { r l } & { \quad \tilde { E } _ { \varphi \varphi } ( \varphi _ { 1 } \otimes \varphi _ { 1 } ) + \tilde { E } _ { \varphi \psi } ( \varphi _ { 1 } \otimes \varphi _ { 0 } \psi + \varphi _ { 0 } \psi \otimes \varphi _ { 1 } ) + \tilde { E } _ { \psi \psi } ( \varphi _ { 0 } \psi \otimes \varphi _ { 0 } \psi ) } \\ & { = \mathcal { E } _ { 1 } ( \varphi _ { 1 } \otimes \varphi _ { 1 } ) + \mathcal { E } _ { 2 } ( \varphi _ { 1 } \otimes \varphi _ { 0 } \psi + \varphi _ { 0 } \psi \otimes \varphi _ { 1 } ) + \mathcal { E } _ { 3 } ( \varphi _ { 0 } \psi \otimes \varphi _ { 0 } \psi ) ; } \end{array}
$$

• At every vertex, we place the linear map $\varphi _ { 1 } ^ { \otimes m } \otimes ( \varphi _ { 0 } \psi ) ^ { \otimes n } \mapsto \tilde { P } _ { g , m , n }$

The base cases are $\begin{array} { r } { \tilde { P } _ { 1 , 0 , 1 } = \frac { \chi ( Z ) } { 2 4 } - 1 } \end{array}$ and $\tilde { P } _ { 0 , 3 } = 1$ . The dilaton equation implies that if $\tilde { P } _ { g , m } \in \tilde { \mathcal { R } }$ , then $\tilde { P } _ { g , m , n } \in \tilde { \mathcal { R } }$ for all $n .$ . Now we assume that $\tilde { P } _ { h , \ell , n } \in \tilde { \mathcal { R } }$ for all $( h , \ell ) < \bar { ( g , m ) }$ . Then we know $f _ { g , m } ^ { \mathbf { B } } \in \mathbb { Q } [ X ]$ by Corollary 4.9. Computing it by the stable graph sum, we see

$$
f _ { g , m } ^ { \mathbf { B } } = \tilde { P } _ { g , m } + \sum _ { \Gamma \mathrm { ~ n o n - l e a d i n g } } \frac { 1 } { | \mathrm { A u t } \Gamma | } \mathrm { C o n t } _ { \Gamma } .
$$

By the inductive hypothesis and the formula for the edge contributions, $\mathrm { C o n t } _ { \Gamma } \in \tilde { \mathcal { R } }$ for any non-leading Γ. The desired result follows immediately. □

Proof of Theorem 5.1. The second equation (5.2) is equivalent to Theorem 5.6 by the results of [YY04], so we only need to prove (5.1). We proceed by diferentiating the quantization action. By definition, we have

$$
e ^ { P ^ { \bf B } ( \hbar , x , y - E _ { \psi } x ) } = e ^ { - \hbar V ^ { \bf B } ( \partial _ { \bf t } , \partial _ { \bf t } ) } e ^ { f ^ { \bf B } ( \hbar , x , y ) } .
$$

Applying $\partial$ being either $\partial _ { A } , \partial _ { B } , \partial _ { B _ { 2 } } , \mathrm { o r } \partial _ { B _ { 3 } }$ , we see that

$$
\begin{array} { c } { { e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } = - \hbar \partial V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) e ^ { V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) } e ^ { f ^ { \mathbf { B } } ( \hbar , x , y ) } } } \\ { { = - \hbar \partial V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) e ^ { \tilde { P } ^ { \mathbf { B } } ( \hbar , x , y ) } . } } \end{array}
$$

Making the change of variables $\mathbf { t } ^ { \prime } = ( x ^ { \prime } , y ^ { \prime } ) : = ( x , y - E _ { \psi } x )$ , we then see that

$$
V ^ { \mathbf { B } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) = { \frac { 1 } { 2 } } E _ { \varphi \varphi } { \frac { \partial ^ { 2 } } { \partial x ^ { \prime 2 } } } + E _ { \varphi \psi } { \frac { \partial ^ { 2 } } { \partial x ^ { \prime } \partial y ^ { \prime } } } + E _ { \psi \psi } { \frac { \partial ^ { 2 } } { \partial y ^ { \prime 2 } } } = : V ^ { \mathbf { B } , \mathrm { s m a l l } } ( \partial _ { \mathbf { t } ^ { \prime } } , \partial _ { \mathbf { t } ^ { \prime } } ) .
$$

From now on, we will replace $x ^ { \prime }$ by x and $y ^ { \prime }$ by y for simplicity. We now see that

$$
e ^ { P ^ { \bf B } ( \hbar , x , y ) } = \partial V ^ { \bf B , s m a l l } ( \partial _ { \bf t } , \partial _ { \bf t } ) e ^ { P ^ { \bf B } ( \hbar , x , y ) } .
$$

First, $\begin{array} { r } { \partial _ { A } V ^ { \mathbf { B } , \mathsf { s m a l l } } ( \partial _ { \mathbf { t } } , \partial _ { \mathbf { t } } ) = \frac { 1 } { 2 } \frac { \partial ^ { 2 } } { \partial x ^ { 2 } } } \end{array}$ , so we obtain

$$
\partial _ { A } P ^ { \bf B } ( \hbar , x , y ) = - \frac { \hbar } { 2 } \frac { \partial ^ { 2 } } { \partial x ^ { 2 } } P ^ { \bf B } ( \hbar , x , y ) - \frac { \hbar } { 2 } \Bigg ( \frac { \partial } { \partial x } P ^ { \bf B } ( \hbar , x , y ) \Bigg ) ^ { 2 } .
$$

Setting $x = y = 0$ , we see that

$$
\sum _ { g \geq 2 } \hbar ^ { g - 1 } \partial _ { A } P _ { g } = - { \frac { 1 } { 2 } } \left( \sum _ { g \geq 2 } \hbar ^ { g - 1 } P _ { g - 1 , 2 } + \left( \sum _ { g _ { 1 } , g _ { 2 } > 0 } \hbar ^ { g _ { 1 } + g _ { 2 } - 1 } P _ { g _ { 1 } } P _ { g _ { 2 } } \right) \right) .
$$

Taking the coeficient of $\hbar ^ { g - 1 }$ on both sides, we obtain (5.1).

## References

[BCOV94] M. Bershadsky, S. Cecotti, H. Ooguri, and C. Vafa. “Kodaira-Spencer theory of gravity and exact results for quantum string amplitudes”. In: Comm. Math. Phys. 165.2 (1994), pp. 311–427. issn: 0010-3616,1432- 0916.

[Beh97] K. Behrend. “Gromov-Witten invariants in algebraic geometry”. In: Invent. Math. 127.3 (1997), pp. 601–617. issn: 0020-9910,1432-1297. doi: 10.1007/s002220050132.

[BF97] K. Behrend and B. Fantechi. “The intrinsic normal cone”. In: Invent. Math. 128.1 (1997), pp. 45–88. issn: 0020-9910,1432-1297. doi: 10.100 7/s002220050136.

[CCK15] Daewoong Cheong, Ionut¸ Ciocan-Fontanine, and Bumsig Kim. “Orbifold quasimap theory”. In: Math. Ann. 363.3-4 (2015), pp. 777–816. issn: 0025-5831,1432-1807. doi: 10.1007/s00208-015-1186-z.

[CCLT09] Tom Coates, Alessio Corti, Yuan-Pin Lee, and Hsian-Hua Tseng. “The quantum orbifold cohomology of weighted projective spaces”. In: Acta Math. 202.2 (2009), pp. 139–193. issn: 0001-5962,1871-2509. doi: 10.1 007/s11511-009-0035-x.

[CG07] Tom Coates and Alexander Givental. “Quantum Riemann-Roch, Lefschetz and Serre”. In: Ann. of Math. (2) 165.1 (2007), pp. 15–53. issn: 0003-486X,1939-8980. doi: 10.4007/annals.2007.165.15.

[CGL19] Huai-Liang Chang, Shuai Guo, and Jun Li. BCOV’s Feynman rule of quintic 3-folds. 2019. arXiv: 1810.00394.

[CGL21] Huai-Liang Chang, Shuai Guo, and Jun Li. “Polynomial structure of Gromov-Witten potential of quintic 3-folds”. In: Ann. of Math. (2) 194.3 (2021), pp. 585–645. issn: 0003-486X,1939-8980. doi: 10.4007/a nnals.2021.194.3.1.

[CGLL21] Huai-Liang Chang, Shuai Guo, Jun Li, and Wei-Ping Li. “The theory of N-mixed-spin-P fields”. In: Geom. Topol. 25.2 (2021), pp. 775–811. issn: 1465-3060,1364-0380. doi: 10.2140/gt.2021.25.775.

[CL20] Huai-Liang Chang and Jun Li. “A vanishing associated with irregular MSP fields”. In: Int. Math. Res. Not. IMRN 20 (2020), pp. 7347–7396. issn: 1073-7928,1687-0247. doi: 10.1093/imrn/rnaa049.

[CLLL19] Huai-Liang Chang, Jun Li, Wei-Ping Li, and Melissa Chiu-Chu Liu. “Mixed-Spin-P fields of Fermat polynomials”. In: Cambridge Journal of Mathematics 7.3 (2019), pp. 319–364. issn: 2168-0930. doi: 10.4310 /CJM.2019.v7.n3.a3.

[CLLL22] Huai-Liang Chang, Jun Li, Wei-Ping Li, and Chiu-Chu Melissa Liu. “An efective theory of GW and FJRW invariants of quintic Calabi-Yau manifolds”. In: J. Diferential Geom. 120.2 (2022), pp. 251–306. issn: 0022-040X,1945-743X. doi: 10.4310/jdg/1645207466.

[COGP92] Philip Candelas, Xenia C. de la Ossa, Paul S. Green, and Linda Parkes. “A pair of Calabi-Yau manifolds as an exactly soluble superconformal theory”. In: Essays on mirror manifolds. Int. Press, Hong Kong, 1992, pp. 31–95. isbn: 962-7670-01-4.

[CPS18] Emily Clader, Nathan Priddis, and Mark Shoemaker. “Geometric quantization with applications to Gromov-Witten theory”. In: B-model Gromov-Witten theory. Trends Math. Birkh¨auser/Springer, Cham, 2018, pp. 399–462. isbn: 978-3-319-94219-3; 978-3-319-94220-9.

[FO99] Kenji Fukaya and Kaoru Ono. “Arnold conjecture and Gromov-Witten invariant”. In: Topology 38.5 (1999), pp. 933–1048. issn: 0040-9383. doi: 10.1016/S0040-9383(98)00042-1.

[FP00] C. Faber and R. Pandharipande. “Hodge integrals and Gromov-Witten theory”. In: Invent. Math. 139.1 (2000), pp. 173–199. issn: 0020- 9910,1432-1297. doi: 10.1007/s002229900028.

[Giv01] Alexander B. Givental. “Gromov-Witten invariants and quantization of quadratic Hamiltonians”. In: vol. 1. 4. Dedicated to the memory of I. G. Petrovskii on the occasion of his 100th anniversary. 2001, pp. 551–568, 645. doi: 10.17323/1609-4514-2001-1-4-551-568.

[Giv04] Alexander B. Givental. “Symplectic geometry of Frobenius structures”. In: Frobenius manifolds. Vol. E36. Aspects Math. Friedr. Vieweg, Wiesbaden, 2004, pp. 91–112. isbn: 3-528-03206-5.

[Giv96] Alexander B. Givental. “Equivariant Gromov-Witten invariants”. In: Internat. Math. Res. Notices 13 (1996), pp. 613–663. issn: 1073-7928,1687- 0247. doi: 10.1155/S1073792896000414.

[GJR17] Shuai Guo, Felix Janda, and Yongbin Ruan. A mirror theorem for genus two Gromov-Witten invariants of quintic threefolds. 2017. arXiv: 1709.07392.

[GJR18] Shuai Guo, Felix Janda, and Yongbin Ruan. Structure of Higher Genus Gromov-Witten Invariants of Quintic 3-folds. 2018. arXiv: 1812.11908.

[HKQ09] M.-x. Huang, A. Klemm, and S. Quackenbush. “Topological string theory on compact Calabi-Yau: modularity and boundary conditions”. In: Homological mirror symmetry. Vol. 757. Lecture Notes in Phys. Springer, Berlin, 2009, pp. 45–102. isbn: 978-3-540-86374-8.

[Lee09] Y.-P. Lee. “Invariance of tautological equations. II. Gromov-Witten theory”. In: J. Amer. Math. Soc. 22.2 (2009). With an appendix by Y. Iwao and the author, pp. 331–352. issn: 0894-0347,1088-6834. doi: 10.1090/S0894-0347-08-00616-4.

[Lei24a] Patrick Lei. Higher-genus Gromov-Witten theory of one-parameter Calabi-Yau threefolds I: Polynomiality. 2024. arXiv: 2409.11659.

[Lei24b] Patrick Lei. MSP theory for smooth Calabi-Yau threefolds in weighted P<sup>4</sup>. 2024. arXiv: 2409.11660.

[LLY97] Bong H. Lian, Kefeng Liu, and Shing-Tung Yau. “Mirror principle. I”. In: Asian J. Math. 1.4 (1997), pp. 729–763. issn: 1093-6106,1945-0036. doi: 10.4310/AJM.1997.v1.n4.a5.

[LT98a] Jun Li and Gang Tian. “Virtual moduli cycles and Gromov-Witten invariants of algebraic varieties”. In: J. Amer. Math. Soc. 11.1 (1998), pp. 119–174. issn: 0894-0347,1088-6834. doi: 10.1090/S0894-0347-9 8-00250-1.

[LT98b] Jun Li and Gang Tian. “Virtual moduli cycles and Gromov-Witten invariants of general symplectic manifolds”. In: Topics in symplectic 4-manifolds (Irvine, CA, 1996). Vol. I. First Int. Press Lect. Ser. Int. Press, Cambridge, MA, 1998, pp. 47–83. isbn: 1-57146-019-5.

[Pop13] Alexandra Popa. “The genus one Gromov-Witten invariants of Calabi-Yau complete intersections”. In: Trans. Amer. Math. Soc. 365.3 (2013), pp. 1149–1181. issn: 0002-9947,1088-6850. doi: 10.1090/S0002-9947- 2012-05550-4.

[PPZ15] Rahul Pandharipande, Aaron Pixton, and Dimitri Zvonkine. “Relations on ${ \overline { { \mathcal { M } } } } _ { g , n }$ via 3-spin structures”. In: J. Amer. Math. Soc. 28.1 (2015), pp. 279–309. issn: 0894-0347,1088-6834. doi: 10.1090/S0894-0347-2 014-00808-0.

[RT95] Yongbin Ruan and Gang Tian. “A mathematical theory of quantum cohomology”. In: J. Diferential Geom. 42.2 (1995), pp. 259–367. issn: 0022-040X,1945-743X.

[Rua99] Yongbin Ruan. “Virtual neighborhoods and pseudo-holomorphic curves”. In: Proceedings of 6th G¨okova Geometry-Topology Conference. Vol. 23. 1. 1999, pp. 161–231.

[Sie98] Bernd Siebert. Gromov-Witten invariants of general symplectic manifolds. 1998. arXiv: dg-ga/9608005.

[Wan20] Jun Wang. A mirror theorem for Gromov-Witten theory without convexity. 2020. arXiv: 1910.14440.

[YY04] Satoshi Yamaguchi and Shing-Tung Yau. “Topological string partition functions as polynomials”. In: J. High Energy Phys. 7 (2004), pp. 047, 20. issn: 1126-6708,1029-8479. doi: 10.1088/1126-6708/2004/07/047.

[Zho22] Yang Zhou. “Quasimap wall-crossing for GIT quotients”. In: Invent. Math. 227.2 (2022), pp. 581–660. issn: 0020-9910,1432-1297. doi: 10.1 007/s00222-021-01071-z.

[Zin09] Aleksey Zinger. “The reduced genus 1 Gromov-Witten invariants of Calabi-Yau hypersurfaces”. In: J. Amer. Math. Soc. 22.3 (2009), pp. 691– 737. issn: 0894-0347,1088-6834. doi: 10.1090/S0894-0347-08-00625 -5.