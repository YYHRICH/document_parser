## OUJ-FTC-11

## Notes on the Exact RG equation and the Wheeler-DeWitt equation

Hideto Kamei 1

Field theory group, The Open University of Japan, Chiba 261-8586, Japan

February 25, 2024

In this note, in the context of the AdS/CFT correspondence, the holographic derivation of the Wilsonian effective action is proposed. Then, the exact RG equation in the boundary theory is derived from the Wheeler-DeWitt equation of the bulk, following the suggestion of [1],[2], and[3]. The relationship between the exact RG and Stochastic Quantization[4],[5] is briefly discussed.

## 1 Introduction

Here in this note, we would like to promote Holographic RG to exact RG, which corresponds to quantum gravity in the bulk. By Verlinde et al [1], it was shown that the RG flow equation of the CFT can be derived from classical Equation of motion of the bulk 2 . We generalize the RG flow equation to exact RG, which is derived from Wheeler-Dewitt equation in the bulk. We identify the expression of the boundary action and counterterm is properly subtracted in the derivation.

Now we outline the structure of this note. In section 2, the setup of the derivation is given. In section 3, the role of the boundary condition in the setup is explained. In section 4, procedure for splitting the bulk action and identifying the boundary action is given. In section 5, derivation of the exact RG equation from the bulk is given. In section 6, interpretation of the equation as the exact RG is given. In section 7, an example to show the validity of the methodology is given. In section 8, discussion on the result and possible future research is given. In section 9, update on research since this note was first written is given.

1 hidetokamei@gmail.com

2 For a review, please refer to [6].

## 2 Deriving the exact RG from the bulk theory

Here we wish to derive the exact renormalization group equation (In the form of [7],[8],[9],[10]) of N = 4 SYM from the Wheeler-DeWitt equation in the AdS. Most of the discussion follows from the beautiful paper on the holographic renormalization, [1]. In the paper, the CallanSymanzik type of the RG flow equation was derived from the condition that the Hamiltonian is zero, H = 0, and the Wheeler-DeWitt equation is the quantum extension of H = 0.

We assume that the bulk action contains gravity and a scalar field (the extension to including many scalar fields and including other fields is straightforward). We take the parametrization of the 5d metric as,

[[FORMULA_UNAVAILABLE]]

We will work in the Euclidean signature everywhere in this note. Here we fix the gauge of the metric as N = 1 , N i = 0. We decompose the Ricci scalar using extrinsic curvature,

[[FORMULA_UNAVAILABLE]]

From now on we treat the metric as fields and use the condensed notation, h ij ≡ h I , K ij ≡ K I . Further we will use so-called DeWitt's supermetric G IJ ≡ G ijkl ≡ √ h ( 1 2 ( h ik h jl + h il h jk ) -h ij h kl ) and its inverse G IJ for the condensed notation of the action. We can define the conjugate momentum of the metric and the scalar field as π I = δ L /δ∂ r h I , and p = δ L /δ∂ r φ , and construct the Hamiltonian H = π I ∂ r h I + p∂ r φ -L . The equation we wish to solve is the Wheeler-DeWitt equation, which is H Ψ = 0. Analogous to the Shr¨ odinger equation, we simply have to replace momentum π I , p with the derivative δ/δh I , δ/δφ . We wish to proceed following [2] to derive the exact RG equation of the CFT holgraphically. In the classical case, we will get the expression of the radial velocity of the fields (with respect to the 4d action) from Hamilton-Jacobi equation,

[[FORMULA_UNAVAILABLE]]

and in the quantum case the same equation holds for field redefinition, but we will need a correction term F ( φ ) as in (6.1), which will be consistent with Wheeler-DeWitt equation (5.4) we will derive.

## 3 The role of the boundary condition and the fluctuation

Here in this section, we would like to explain the role of the boundary condition in terms of the fluctuation in the boundary CFT, in order to motivate the holographic definition of the Wilsonian effective action in the following section.

First of all, we would like to claim that the boundary value of the bulk fields themselves could be considered as the dynamical fields in the boundary CFT in some cases. The main example we consider in this note is a scalar field in the AdS within the mass range -d 2 / 4 &lt; m 2 &lt; -( d 2 / 4) + 1. In this mass range, it is known, in addition to the standard Dirichlet boundary condition, we can also impose free boundary condition[11],[12],[13],[14],[15], and it is called 'alternative quantization'. Those two different boundary conditions correspond to different CFTs on the boundary, CFT D and CFT F respectively. In the case of free boundary condition, we also need to integrate over the value of the boundary condition of the bulk field, and therefore, the partition function of the CFT F can be obtained by promoting the source in the CFT D to a dynamical field and integrating over it as

[[FORMULA_UNAVAILABLE]]

This expression can be interpreted as the path integral formally (or statistical partition function if one wishes), where J is now a dynamical field, and weight is exp( -Γ[ J ]), Γ being the generating functional for CFT D . Therefore, in the case of the free boundary condition, the boundary value of the bulk field can be considered as the field in the boundary CFT itself, and we can consider an exact RG with respect to that. 3 In addition, also for other fields, it is known that in the free boundary condition (or equivalently Neumann boundary condition in the classical limit), the bulk fields on the boundary are interpreted as the dynamical fields in the boundary CFT.[16],[17].

Another example for the free boundary condition is, trailing string in the AdS[18],[19]. We consider a string stretching from the horizon of the black brane to the boundary at the finite radial distance. The endpoint on the boundary is identified as the position of a particle in the CFT. Since the boundary is at the finite radial distance, the fluctuation of the string in the bulk can be transferred to the fluctuation of the endpoint, which is the fluctuation of the particle in the CFT. Therefore, we need to sum over all the possible value of the boundary position of the string, and it is formally the same as the path integral for the position of the particle in the CFT. Therefore, in the case of the trailing string, we also take the free boundary condition, and the boundary condition is promoted to a dynamical field in the boundary. we expect, if we take the boundary at the finite radial distance[2], boundary value of the closed string modes in the bulk might be also identified as the fields of the closed string modes of the boundary theory.

3 Necessity of the free boundary condition was first realized by the necessity of having operator with small conformal dimension, which can't be realized by the naive Dirichlet boundary condition. Later it was realized those two CFTs are connected by an RG flow, by adding relevant perturbation f O 2 , where O is an operator to couple the source. (3.1) was obtained using that relationship.

Therefore, we claimed that, in some cases in the AdS/CFT, free boundary condition naturally arise and the integration over the boundary condition could be formally identified as the path integral in the boundary CFT. The above discussion will not be precise enough, but hopefully enough to motivate the following holographic definition of the Wilsonian effective action.

## 4 The definition of the boundary Wilsonian effective action from the bulk

When we define the Wilsonian effective action of the CFT side, we observe the CFT side with respect to a particular energy scale. In the context of AdS/CFT, it would be natural to concentrate on a hypersurface in the AdS, which will manifest the physics of the CFT side with respect to a particular energy scale we observe the physics [1]. There the radial coordinate in the AdS is related to the energy scale of the observation in the CFT side. Let's take the hypersurface as r = const . Then, following [3], the total partition function of the bulk, which is also equal to the total partition of the CFT, can be written as the path integral over the fields on this boundary, and fields in the region of larger r than this hypersurface (I denote it as UV, since it corresponds to the UV degree of freedom in the CFT side), and fields in the smaller r region (I denote it as IR). Then, we can separate the expression of the bulk gravity action into UV part and IR part, since there is no cross term in the action for the fields with different r . Note that they are still the function of the Dirichlet boundary condition on the hypersurface.

[[FORMULA_UNAVAILABLE]]

We can first perform the path integral for the fields of the UV and the IR part, and it will give the result of the second line. We expressed the UV part of the partition function, or wave function as Ψ UV ( r, φ r ) = exp( -S bulk UV ( r, φ )), and IR part of the wave function as Ψ IR ( r, φ r ) = exp( -S bulk IR ( r, φ )). Further, we can define the total low energy effective action as exp( -S ( r, φ r )) ≡ Ψ UV ( r, φ r )Ψ IR ( r, φ r ), which is the function of the boundary condition at r . The last line of (4.1) looks like the expression of the CFT partition function, with respect to the effective field φ r and Wilsonian effective action S ( r, φ r ), and it is tempting to define the Wilsonian effective action at some energy scale, which is determined by r , as simply this S ( r, φ r ), holographically. Indeed, defining this way, we can show this 'Wilsonian effective action' will follow the Exact RG equation with respect to the change of the energy scale, which is the boundary position r in the bulk. This is given by solving the Wheeler-DeWitt equation in the bulk, which is the quantum extension of the condition that the Hamiltonian is zero for the gravity. Also note, that the above definition of the Wilsonian effective action, reduces to the definition of [15] in the bulk classical limit, as it should.

## 5 Holographic Exact RG at finite radial distance

Let's then derive the exact RG equation from the WDW equation in the bulk following the spirit of [2]. To make a contact with Polchinski type[20] of the Exact RG, let's first consider the regime where we can treat the metric as the classical background, and concentrate on the quantized scalar field in the AdS. This is done by recovering the Newton's constant G N to the Wheeler-DeWitt equation, and expanding it with G N . This is done following [21].

The Wheeler-DeWitt equation is,

[[FORMULA_UNAVAILABLE]]

Both UV and IR wavefunction, Ψ UV and Ψ IR are expected to satisfy the above WDW equation separately. Here we assume that V is a constant (which doesn't depend on φ ), and H matter = ( p 2 / 2) + W ( φ ) -Φ( φ ) R + (1 / 2)( ∂ i φ ) 2 , where W ( φ ) is the φ dependent part of the 5d potential, and its order φ 2 has the coefficient m 2 / 2 which satisfies the bound that we discussed. We assume that H matter is the order of O ( G 0 N ). We further assume that we can expand S = -log Ψ as S = ( S 0 / 16 πG N ) + S 1 + O ( G 1 N ), and suppose S 0 depends only on the metric, and not on the scalar field. By expanding the Wheeler-DeWitt equation for O ( G -1 N ), while still seperating S 0 into the UV part and the IR part with respect to the cutoff, we get

[[FORMULA_UNAVAILABLE]]

Note that the indices of the metric h I are implicitly contracted in the above expression. Strictly speaking, δ 2 S/δh 2 term is order O ( G 0 N ), but we added it for simplicity of the next order [21]. This form of the 5d potential implies that the bulk gravity could be constructed out of the Stochastic Quantization 4 , -∂ r h I = -G IJ ( δS UV /δh J ) + E I a ξ a , where ξ a is the gaussian noise and E is the inverse of the vielbein for G IJ [23]. For O ( G 0 N ), we get

4 Please refer to [22] for an analogous discussion.

[[FORMULA_UNAVAILABLE]]

Let's derive the exact RG equation from the above equation of motion (5.3). We use the right hand side and the left hand side of the equality, and use δS 0 UV /δh + δS 0 IR /δh = 0, because S 0 is classical, purely gravitational part of the action, and the configuration of the metric h should minimize this. (See [2]) Remember that now the scalar field φ is quantized and we can't naively consider its classical trajectory. We have the classical gravity background, and we parameterize the physical scale by the overall factor of the metric. By parameterizing h ij = e 2 a δ ij , ' -a ' can be considered as the parameter for the RG flow.

[[FORMULA_UNAVAILABLE]]

Here we have assumed the behavior of the metric h is determined by the leading order of the action S UV = S 0 UV / 16 πG N , together with (2.3).

The above expression is a class of the exact RG equation presented in [7],[8],[10]. Please remember, in order to identify the above equation as the exact RG, we needed to identify the boundary value of the bulk field as the dynamical field on the boundary CFT as well. At least it is formally true in some cases of AdS/CFT where we can take free boundary condition, there we integrate over all the possible configuration of the boundary value of the bulk field, and it was treated as a dynamical field on the boundary [15], [14]. Moreover, when we put the boundary at the finite radial distance, the boundary condition of the stochastic string [19], [18] and graviton [2] were identified as the dynamical field on the boundary. However, in order to justify it from the field theory, we would need to show that the effective action can be thought of as a classical action, and that the value of the one-point function can be thought of as the value of the field, and that those fields are the fundamental degree of freedom. We will probably need the discussion about the large N field theory as a classical theory [24], [25], and about the formulation of the gauge theory in terms of Wilson loop [26].

Note that the expression (5.4) can be thought of as a Fokker-Planck equation if we identify -da or -dr as time, and identify probability density as P = exp( -S 1 ), and if S UV is nearly constant with respect to r (In the regime of CFT). It implies that it would be also possible to formulate this exact RG equation as a Langevin equation [27], -∂ a φ = -δS UV /δφ + ξ , or in terms of the boundary CFT, S UV will be replaced by the generating functional Γ[ φ ].

## 6 From the viewpoint of the Exact RG

Let's see that the expression we have obtained in the last section is actually the exact RG equation in the field theory. First of all, any RG flow equation are obtained from two steps, coarse-graining the microscopic degree of freedom and rescaling. In the continuum field theory, it is known that the coarse-graining step can be simply performed by redefinition of the field[10]. Therefore, we consider the conformal transformation (scale transformation) of the fields in the CFT, and in addition, we perform extra transformation on scalar field as F ( φ ) dr , which will correspond to the coarse-graining. The transformation of the fields will be then,

[[FORMULA_UNAVAILABLE]]

We now assume that the change of the effective action S 1 is solely due to the change of the field, and the functional form of S 1 doesn't change, as in the regular derivation of the exact RG. We can write down the Wilsonian effective action S 1 ( φ ′ , h ′ ) with respect to the new fields φ ′ , h ′ , and by definition it should satisfy

[[FORMULA_UNAVAILABLE]]

Expanding the left hand side with respect to φ , h , and collecting terms of the order O ( dr ), we get

[[FORMULA_UNAVAILABLE]]

If we choose F = -1 2 δS 1 δφ , this expression is precisely what we have obtained from the Wheeler-DeWitt equation in the bulk,(5.4). The form of the field transformation for the coarse graining F is intuitively reasonable, because, if we see it in the form of the Langevin equation in the previous section, this term corresponds to the noise, therefore it will look like it is washing out microscopic degree of freedom, as any RG should. It was interpreted in [27] that this noise term corresponds to the contribution from irrelevant operators.

## 7 Example: Flow of the double trace operator

We then still consider the alernative quantization, in which the bulk operators are interpreted as the boundary operator at some RG scale. We mostly follow the discussion in [3] and [15]. We assume that the bulk action is of gaussian form, potential containing only mass term. We take gaussian ansatz for S UV and S IR as a function of the boundary value of the fields φ and the coordinate z . (Note that z can be also understood as the scale parameter from the coordinate dependence of the metric, h ij ∼ z -2 δ ij .) The expression of the action for the UV part and the IR part respectively, are

[[FORMULA_UNAVAILABLE]]

[[FORMULA_UNAVAILABLE]]

We then wish to consider the flow of the double trace operator, which will correspond to the coefficient of the φ 2 term in S = S UV + S IR , since, according to the recipe of [1], the sum of the UV and IR action should be identified as the CFT effective action. We will need to see the bulk equation of motion for the evolution of F = F UV + F IR , and we can compute F UV and F IR respectively from the Schr¨ odinger equation as computed in [3]. Actually, since we restrict the form of the action to the Gaussian, there is no quantum correction to the double trace operator, (because ( δS 2 /δφ 2 ) term will have only constant O ( φ 0 ) term) and therefore we can look at Hamilton-Jacobi equation ( H = z∂ z S UV = (1 / 2 √ h ) p 2 +( √ h/ 2)( z 2 δ ij k i k j φ 2 + m 2 φ 2 )). Then we will get 5

This equation can be solved by F UV = z∂ z O / O , where O is the Bessel function which solves

[[FORMULA_UNAVAILABLE]]

The above F UV , for kz ≪ 1, gives

[[FORMULA_UNAVAILABLE]]

Note that the behavior of F UV for small/large z is as expected, because it should follow the conformal scaling with ∆ -, ∆ + . On the other hand, we can also obtain F IR from the condition that the solution will not blow up at z →∞ , and get

[[FORMULA_UNAVAILABLE]]

When k ∼ 0, it can be approximated as F IR ∼ -∆ -. Therefore, if the identification of the total bulk action as the CFT effective action (as [1]) is correct, F , sum of F UV and F IR , should give the right coefficient for the double trace operator, and it is

[[FORMULA_UNAVAILABLE]]

Behavior of F at small z , F ∼ z 2 ν , is as expected from the conformal dimention of the coupling of the double trace operator. It is also confirmed that this F ∼ F UV -∆ -follows the same equation as the flow of the coupling of the double trace operator [15]. Here we wish to derive the same equation from a different perspective, from the exact RG flow equation that we have derived. By rewriting (5.4) with respect to S and S IR , and concentrating on φ 2 term, we will get an equation

5 Note that the below result differ from [3] since their definition of F includes √ h as well.

[[FORMULA_UNAVAILABLE]]

which is the same equation as in [15] up to different definition of F by factor of minus sign. We can see that the derivation of the RG flow equation of the double trace operator naturally arises in our case (summing over UV part and IR part of the action). It still remains to be done what will be the modification of the RG flow equation (7.7) for general k .

## 8 Discussion

Therefore, we gave the holographic definition of the Wilsonian effective action, and derived the exact RG flow equation from the Wheeler-DeWitt equation in the bulk, when we can take free boundary condition for the bulk scalar field. The fact, that we could derive the exact RG from the quantum evolution of the bulk, could be convinced in light of stochastic quantization, which also realize the holographic setup; Firstly, It was proposed that the exact RG equation is equivalent to Stochastic RG equation, which looks like Langevin equation, where the scale plays the role of 'time'. (See [27] 6 . This RG is basically equivalent to Stochastic Quantization.) and also, in the context of the Stochastic quantization, the noise of the Langevin equation along the 'extra dimension' on the boundary is corresponding to the Quantum fluctuation of the bulk. Summing up those ingredients, we can convince myself that there is a good reason to suspect the quantum evolution of the bulk is related to the 'Stochastic RG', or exact RG of the boundary theory. Partial evidence that the Wheeler-DeWitt equation is related to the exact RG equation also comes from [3], where they use the Schr¨ odinger equation of the bulk to derive the exact RG. Moreover, in the context of the gauge theory of the boundary, the connection between the exact RG and Schwinger-Dyson equation was made [29], and in addition, it was proposed that the Schwinger-Dyson equation of the boundary is related to the Wheeler-DeWitt equation of the string theory [30]. This gauge theory discussion also suggests the relationship between the Wheeler-DeWitt equation and the exact RG.

This result will hopefully give a better understanding on how exact RG is related to the quantized gravity, and in relating the holographic RG and Polchinski RG. Also, we wish that there will be more understanding of Holography in terms of Stochastic Quantization as exact RG, which was only implied here. If this identification is established, we will be able to perform the exact RG in a much simpler way, because many miracles, such as no need of gauge-fixing, no need of putting the cutoff, simplification for large N and natural apperance of supersymmetry so on, happens in the stochastic quantization. Note that the same analysis would be applicable to Horava gravity, since they are constructed out of the stochastic quantization, and the stochastic quantization is equivalent to a class of exact RG. It was explained that the structure of stochastic quantization enables the simpler proof of its renormalizability[23], and we expect that might apply to other general holographic models. Further it was implied that the quantized gravity in the bulk will be written as Langevin equation, which might give more insights into microscopic picture for thermodynamics of spacetime[31], [32].

6 The apperence of Langevin equation in the context of RG is not limited to Field Theory. See[28], there they also show that Langevin equation appears as the result of RG

## 9 Update on recent research

Since this note was originally written more than 10 years ago, there have been a number of recent studies [33][34],[35],[36],[37],[38],[39],[40][41], that need to be mentioned. Some of them [33][34] view the holographic setting in a similar way by splitting to UV part and IR part, although they are based on standard quantization and consider the gravity action after it is integrated over quantum fluctuation. A series of studies [36],[37],[38],[39],[40],[41] start from the exact RG equation and express transition amplitudes between wave functions of different scale as ∫ D x ( t ) e -S bulk , where x ( t ) denotes fields at different scale t , and regard S bulk as the bulk action. They also mention that some of their derivation corresponds to alternative quantization[37], and the relationship between Holographic exact RG and Stochastic Quantization[40]. The goal of relating the exact RG to the bulk quantum gravity is the same, although they are working on deriving the bulk theory without using explicitly holographic setting. This note is different in working with alternative quantization and using holographic setting, deriving the exact RG equation on the boundary from the evolution of the wave function in the bulk, dealing with the counterterm. There are also a number of studies that relate Stochastic Quantization and Holography[42],[43],[44],[45],[46],[47]. In particular, [43],[44],[45],[46],[47] identify radial evolution in the bulk to Stochastic Quantization, which is the exact RG on the boundary, and also derives the evolution of double trace operator, so they are practically very similar to this note. However, their derivation is different from the one in this note, in particular how to subtract the counterterm. To note, in addition to the research above, we were recently informed that there is another study that mentions the resemblance between the exact RG and Fokker-Planck equation[48].

## Acknowledgements

I would like to thank Gilad Lifschitz, Akio Sugamoto and So Katagiri for helpful comments, and those who answered my questions on holography and exact RG.

## References

- [1] J. de Boer, E. P. Verlinde and H. L. Verlinde, 'On the holographic renormalization group,' JHEP 0008 (2000) 003 [arXiv:hep-th/9912012].
- [2] E. P. Verlinde and H. L. Verlinde, 'RG-flow, gravity and the cosmological constant,' JHEP 0005 , 034 (2000) [arXiv:hep-th/9912018].
- [3] I. Heemskerk and J. Polchinski, 'Holographic and Wilsonian Renormalization Groups,' arXiv:1010.1264 [hep-th].
- [4] G. Parisi and Y. s. Wu, 'Perturbation Theory Without Gauge Fixing,' Sci. Sin. 24 , 483 (1981).
- [5] P.H.Damgaard and H.Huffel, 'STOCHASTIC QUANTIZATION,' SINGAPORE, SINGAPORE: WORLD SCIENTIFIC (1988) 496p ,
- [6] M. Fukuma, S. Matsuura and T. Sakai, 'Holographic renormalization group,' Prog. Theor. Phys. 109 , 489 (2003) [arXiv:hep-th/0212314].
- [7] T. R. Morris, 'The Exact renormalization group and approximate solutions,' Int. J. Mod. Phys. A 9 , 2411 (1994) [arXiv:hep-ph/9308265].
- [8] T. R. Morris, 'A manifestly gauge invariant exact renormalization group,' arXiv:hep-th/9810104.
- [9] J. I. Latorre and T. R. Morris, 'Exact scheme independence,' JHEP 0011 , 004 (2000) [arXiv:hep-th/0008123].
- [10] O. J. Rosten, 'Fundamentals of the Exact Renormalization Group,' arXiv:1003.1366 [hepth].
- [11] I. R. Klebanov and E. Witten, 'AdS/CFT correspondence and symmetry breaking,' Nucl. Phys. B 556 , 89 (1999) [arXiv:hep-th/9905104].
- [12] W. Mueck and K. S. Viswanathan, 'Regular and irregular boundary conditions in the AdS/CFT correspondence,' Phys. Rev. D 60 , 081901 (1999) [arXiv:hep-th/9906155].
- [13] E. Witten, 'Multi-trace operators, boundary conditions, and AdS/CFT correspondence,' arXiv:hep-th/0112258.
- [14] E. Witten, 'SL(2,Z) action on three-dimensional conformal field theories with Abelian symmetry,' arXiv:hep-th/0307041.

- [15] T. Faulkner, H. Liu, M. Rangamani, 'Integrating out geometry: Holographic Wilsonian RG and the membrane paradigm,' [arXiv:1010.4036 [hep-th]].
- [16] O. Aharony, D. Marolf and M. Rangamani, 'Conformal field theories in anti-de Sitter space,' JHEP 1102 , 041 (2011) [arXiv:1011.6144 [hep-th]].
- [17] D. Marolf and S. F. Ross, 'Boundary conditions and new dualities: Vector fields in AdS/CFT,' JHEP 0611 , 085 (2006) [arXiv:hep-th/0606113].
- [18] J. de Boer, V. E. Hubeny, M. Rangamani et al. , 'Brownian motion in AdS/CFT,' JHEP 0907 , 094 (2009). [arXiv:0812.5112 [hep-th]].
- [19] D. T. Son, D. Teaney, 'Thermal Noise and Stochastic Strings in AdS/CFT,' JHEP 0907 , 021 (2009). [arXiv:0901.2338 [hep-th]].
- [20] J. Polchinski, 'Renormalization And Effective Lagrangians,' Nucl. Phys. B 231 , 269 (1984).
- [21] G. Lifschytz, S. D. Mathur and M. Ortiz, 'A Note on the semiclassical approximation in quantum gravity,' Phys. Rev. D 53 , 766 (1996) [arXiv:gr-qc/9412040].
- [22] T. Nishioka, 'Horava-Lifshitz Holography,' Class. Quant. Grav. 26 , 242001 (2009) [arXiv:0905.0473 [hep-th]].
- [23] D. Orlando and S. Reffert, 'On the Renormalizability of Horava-Lifshitz-type Gravities,' Class. Quant. Grav. 26 , 155021 (2009) [arXiv:0905.0301 [hep-th]].
- [24] L. G. Yaffe, 'Large N Limits As Classical Mechanics,' Rev. Mod. Phys. 54 , 407 (1982).
- [25] J. L. F. Barbon, 'Multitrace AdS/CFT and master field dynamics,' Phys. Lett. B 543 , 283 (2002) [arXiv:hep-th/0206207].
- [26] Y. Makeenko, 'Large-N gauge theories,' arXiv:hep-th/0001047.
- [27] J. C. Gaite, 'Stochastic formulation of the renormalization group: Supersymmetric structure and topology of the space of couplings,' J. Phys. A 37 , 10409 (2004) [arXiv:hep-th/0404212].
- [28] Some implications of renormalization group theoretical ideas to statistics Physica D: Nonlinear Phenomena, Volume 205, Issue 1-4, June 2005, Pages 207-214 Rajaram, S.; Taguchi, Y.h.; Oono, Y.
- [29] S. Hirano, 'Exact renormalization group and loop equation,' Phys. Rev. D 61 , 125011 (2000) [arXiv:hep-th/9910256].

- [30] G. Lifschytz and V. Periwal, 'Schwinger-Dyson = Wheeler-DeWitt: Gauge theory observables as bulk operators,' JHEP 0004 , 026 (2000) [arXiv:hep-th/0003179].
- [31] T. Jacobson, 'Thermodynamics of space-time: The Einstein equation of state,' Phys. Rev. Lett. 75 , 1260 (1995) [arXiv:gr-qc/9504004].
- [32] E. P. Verlinde, 'On the Origin of Gravity and the Laws of Newton,' arXiv:1001.0785 [hep-th].
- [33] S. J. Sin and Y. Zhou, 'Holographic Wilsonian RG Flow and Sliding Membrane Paradigm,' JHEP 05 , 030 (2011) doi:10.1007/JHEP05(2011)030 [arXiv:1102.4477 [hep-th]].
- [34] V. Balasubramanian, M. Guica and A. Lawrence, 'Holographic Interpretations of the Renormalization Group,' JHEP 01 , 115 (2013) doi:10.1007/JHEP01(2013)115 [arXiv:1211.1729 [hep-th]].
- [35] R. G. Leigh, O. Parrikar and A. B. Weiss, 'Exact renormalization group and higherspin holography,' Phys. Rev. D 91 , no.2, 026002 (2015) doi:10.1103/PhysRevD.91.026002 [arXiv:1407.4574 [hep-th]].
- [36] B. Sathiapalan and H. Sonoda, 'A Holographic form for Wilson's RG,' Nucl. Phys. B 924 , 603-642 (2017) doi:10.1016/j.nuclphysb.2017.09.018 [arXiv:1706.03371 [hep-th]].
- [37] B. Sathiapalan and H. Sonoda, 'Holographic Wilson's RG,' Nucl. Phys. B 948 , 114767 (2019) doi:10.1016/j.nuclphysb.2019.114767 [arXiv:1902.02486 [hep-th]].
- [38] B. Sathiapalan, 'Holographic RG and Exact RG in O(N) Model,' Nucl. Phys. B 959 , 115142 (2020) doi:10.1016/j.nuclphysb.2020.115142 [arXiv:2005.10412 [hep-th]].
- [39] P. Dharanipragada, S. Dutta and B. Sathiapalan, 'Bulk gauge fields and holographic RG from exact RG,' JHEP 23 , 174 (2020) doi:10.1007/JHEP02(2023)174 [arXiv:2201.06240 [hep-th]].
- [40] P. Dharanipragada, S. Dutta and B. Sathiapalan, 'Aspects of the map from exact RG to holographic RG in AdS and dS,' Mod. Phys. Lett. A 37 , no.37n38, 2250235 (2022) doi:10.1142/S0217732322502352 [arXiv:2301.13605 [hep-th]].
- [41] P. Dharanipragada and B. Sathiapalan, 'Holographic RG from ERG: Locality and General Coordinate Invariance in the Bulk,' [arXiv:2306.07442 [hep-th]].
- [42] D. S. Mansi, A. Mauri and A. C. Petkou, 'Stochastic Quantization and AdS/CFT,' Phys. Lett. B 685 , 215-221 (2010) doi:10.1016/j.physletb.2010.01.033 [arXiv:0912.2105 [hep-th]].

- [43] J. H. Oh and D. P. Jatkar, 'Stochastic quantization and holographic Wilsonian renormalization group,' JHEP 11 , 144 (2012) doi:10.1007/JHEP11(2012)144 [arXiv:1209.2242 [hep-th]].
- [44] D. P. Jatkar and J. H. Oh, 'Stochastic quantization of conformally coupled scalar in AdS,' JHEP 10 , 170 (2013) doi:10.1007/JHEP10(2013)170 [arXiv:1305.2008 [hep-th]].
- [45] J. H. Oh, 'First-order formalism of holographic Wilsonian renormalization group: Langevin equation,' J. Korean Phys. Soc. 79 , no.10, 903-917 (2021) doi:10.1007/s40042021-00320-x [arXiv:2110.05013 [hep-th]].
- [46] G. Kim, J. s. Chae, W. Shin and J. H. Oh, 'Stochastic quantization and holographic Wilsonian renormalization group of scalar theory with generic mass, self-interaction and multiple trace deformation,' Int. J. Mod. Phys. A 38 , no.21, 2350114 (2023) doi:10.1142/S0217751X23501142 [arXiv:2305.18920 [hep-th]].
- [47] J. H. Lee and J. H. Oh, 'Stochastic quantization and holographic Wilsonian renormalization group of conformally coupled scalar in AdS 4 ,' J. Korean Phys. Soc. 83 , no.9, 665-674 (2023) doi:10.1007/s40042-023-00926-3 [arXiv:2308.10010 [hep-th]].
- [48] Y. Hatta and T. Kunihiro, 'Renormalization group method applied to kinetic equations: Roles of initial values and time,' Annals Phys. 298 , 24-57 (2002) doi:10.1006/aphy.2002.6234 [arXiv:hep-th/0108159 [hep-th]].