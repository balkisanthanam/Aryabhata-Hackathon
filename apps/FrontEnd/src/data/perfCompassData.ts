// Performance Compass Mock Data
// Derived from Design/SampleData/PerfCompassMockData/*.txt
// Student assumed to be in Class 11 — all Class 12 standings are 0 (not started)

// ─── Types ───────────────────────────────────────────────────────────────────

export type Standing = 0 | 1 | 2 | 3 | 4 | 5;
// 0 = Not Started, 1 = Very Poor, 2 = Poor, 3 = Needs Work, 4 = Better, 5 = Well Prepared

export interface SubTopic {
    name: string;
    jeeWeightPct: number;   // % of the chapter's weight attributed to this sub-topic
    studentStanding: Standing;
}

export interface Chapter {
    name: string;
    subTopics: SubTopic[];
    jeeWeightPct: number;   // % of total subject weight (within a class)
    studentStanding: Standing; // avg of sub-topic standings (ignoring 0s), rounded
}

export interface Subject {
    name: string;
    chapters: Chapter[];
    jeeWeightPct: number;   // always 100 within a class-subject
    studentStanding: Standing; // avg of chapter standings (ignoring 0s), rounded
}

export interface ClassData {
    class: '11' | '12';
    subjects: Subject[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function avgStanding(standings: Standing[]): Standing {
    const nonZero = standings.filter(s => s > 0);
    if (nonZero.length === 0) return 0;
    const sum = nonZero.reduce<number>((a, b) => a + b, 0);
    return Math.round(sum / nonZero.length) as Standing;
}

function buildChapter(
    name: string,
    jeeWeightPct: number,
    subTopicsRaw: Array<{ name: string; relWeight: number; standing: Standing }>
): Chapter {
    // Normalize sub-topic weights so they sum to jeeWeightPct
    const totalRel = subTopicsRaw.reduce((s, t) => s + t.relWeight, 0);
    const subTopics: SubTopic[] = subTopicsRaw.map(t => ({
        name: t.name,
        jeeWeightPct: Math.round((t.relWeight / totalRel) * jeeWeightPct * 10) / 10,
        studentStanding: t.standing,
    }));

    return {
        name,
        jeeWeightPct,
        subTopics,
        studentStanding: avgStanding(subTopics.map(s => s.studentStanding)),
    };
}

function buildSubject(name: string, chapters: Chapter[]): Subject {
    return {
        name,
        chapters,
        jeeWeightPct: 100,
        studentStanding: avgStanding(chapters.map(c => c.studentStanding)),
    };
}

// ─── Class 11 Physics ────────────────────────────────────────────────────────

const phy11Chapters: Chapter[] = [
    buildChapter('Units and Measurement', 2, [
        { name: 'The International System of Units', relWeight: 2, standing: 4 },
        { name: 'Significant Figures', relWeight: 2, standing: 3 },
        { name: 'Dimensions of Physical Quantities', relWeight: 3, standing: 4 },
        { name: 'Dimensional Analysis and Applications', relWeight: 3, standing: 3 },
    ]),
    buildChapter('Motion in a Straight Line', 5, [
        { name: 'Instantaneous Velocity and Speed', relWeight: 3, standing: 3 },
        { name: 'Acceleration', relWeight: 3, standing: 4 },
        { name: 'Kinematic Equations for Uniformly Accelerated Motion', relWeight: 5, standing: 4 },
        { name: 'Relative Velocity', relWeight: 3, standing: 3 },
    ]),
    buildChapter('Motion in a Plane', 7, [
        { name: 'Scalars and Vectors', relWeight: 2, standing: 4 },
        { name: 'Addition and Subtraction of Vectors', relWeight: 3, standing: 3 },
        { name: 'Resolution of Vectors', relWeight: 3, standing: 4 },
        { name: 'Projectile Motion', relWeight: 5, standing: 3 },
        { name: 'Uniform Circular Motion', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Laws of Motion', 10, [
        { name: "Newton's First Law of Motion", relWeight: 2, standing: 5 },
        { name: "Newton's Second Law of Motion (F=ma)", relWeight: 4, standing: 4 },
        { name: "Newton's Third Law of Motion", relWeight: 2, standing: 5 },
        { name: 'Conservation of Momentum', relWeight: 3, standing: 3 },
        { name: 'Common Forces in Mechanics (Friction)', relWeight: 5, standing: 3 },
        { name: 'Solving Problems — Free-body Diagrams', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Work, Energy and Power', 10, [
        { name: 'Work-Energy Theorem', relWeight: 4, standing: 3 },
        { name: 'Kinetic Energy', relWeight: 3, standing: 4 },
        { name: 'Potential Energy (Gravitational & Spring)', relWeight: 4, standing: 3 },
        { name: 'Conservation of Mechanical Energy', relWeight: 4, standing: 4 },
        { name: 'Power', relWeight: 2, standing: 3 },
        { name: 'Collisions (Elastic & Inelastic)', relWeight: 5, standing: 2 },
    ]),
    buildChapter('Systems of Particles and Rotational Motion', 10, [
        { name: 'Centre of Mass', relWeight: 3, standing: 3 },
        { name: 'Angular Velocity and Linear Velocity', relWeight: 3, standing: 2 },
        { name: 'Torque and Angular Momentum', relWeight: 4, standing: 2 },
        { name: 'Moment of Inertia', relWeight: 5, standing: 1 },
        { name: 'Dynamics of Rotational Motion', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Gravitation', 6, [
        { name: "Kepler's Laws", relWeight: 3, standing: 3 },
        { name: 'Universal Law of Gravitation', relWeight: 3, standing: 4 },
        { name: 'Acceleration Due to Gravity (variation)', relWeight: 3, standing: 3 },
        { name: 'Gravitational Potential Energy', relWeight: 3, standing: 2 },
        { name: 'Escape Speed', relWeight: 3, standing: 3 },
        { name: 'Earth Satellites & Orbital Energy', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Mechanical Properties of Solids', 4, [
        { name: 'Stress and Strain', relWeight: 4, standing: 3 },
        { name: "Hooke's Law & Stress-Strain Curve", relWeight: 3, standing: 4 },
        { name: "Young's / Shear / Bulk Modulus", relWeight: 4, standing: 3 },
        { name: 'Applications of Elastic Behaviour', relWeight: 2, standing: 2 },
    ]),
    buildChapter('Mechanical Properties of Fluids', 6, [
        { name: "Pressure & Pascal's Law", relWeight: 3, standing: 3 },
        { name: "Bernoulli's Principle", relWeight: 4, standing: 2 },
        { name: 'Viscosity', relWeight: 3, standing: 2 },
        { name: 'Surface Tension', relWeight: 4, standing: 3 },
    ]),
    buildChapter('Thermal Properties of Matter', 5, [
        { name: 'Temperature and Heat', relWeight: 2, standing: 4 },
        { name: 'Ideal-Gas Equation', relWeight: 3, standing: 3 },
        { name: 'Thermal Expansion', relWeight: 3, standing: 3 },
        { name: 'Specific Heat Capacity & Calorimetry', relWeight: 3, standing: 4 },
        { name: 'Change of State & Latent Heat', relWeight: 3, standing: 3 },
        { name: 'Heat Transfer (Conduction, Convection, Radiation)', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Thermodynamics', 9, [
        { name: 'First Law of Thermodynamics', relWeight: 4, standing: 3 },
        { name: 'Specific Heat Capacity (Cp, Cv)', relWeight: 3, standing: 3 },
        { name: 'Thermodynamic Processes (Isothermal, Adiabatic, etc.)', relWeight: 5, standing: 2 },
        { name: 'Second Law of Thermodynamics', relWeight: 3, standing: 2 },
        { name: 'Carnot Engine', relWeight: 4, standing: 1 },
    ]),
    buildChapter('Kinetic Theory', 5, [
        { name: 'Kinetic Theory of Ideal Gas', relWeight: 4, standing: 3 },
        { name: 'Law of Equipartition of Energy', relWeight: 3, standing: 2 },
        { name: 'Specific Heat Capacity (Gases)', relWeight: 3, standing: 2 },
        { name: 'Mean Free Path', relWeight: 2, standing: 3 },
    ]),
    buildChapter('Oscillations', 11, [
        { name: 'Simple Harmonic Motion (SHM)', relWeight: 5, standing: 2 },
        { name: 'SHM and Uniform Circular Motion', relWeight: 3, standing: 2 },
        { name: 'Velocity and Acceleration in SHM', relWeight: 4, standing: 1 },
        { name: 'Energy in SHM', relWeight: 4, standing: 2 },
        { name: 'The Simple Pendulum', relWeight: 3, standing: 3 },
    ]),
    buildChapter('Waves', 10, [
        { name: 'Transverse and Longitudinal Waves', relWeight: 3, standing: 3 },
        { name: 'Speed of a Travelling Wave', relWeight: 3, standing: 3 },
        { name: 'Principle of Superposition', relWeight: 4, standing: 2 },
        { name: 'Reflection of Waves', relWeight: 3, standing: 2 },
        { name: 'Beats', relWeight: 4, standing: 3 },
    ]),
];

// ─── Class 11 Chemistry ─────────────────────────────────────────────────────

const chem11Chapters: Chapter[] = [
    buildChapter('Some Basic Concepts of Chemistry', 5, [
        { name: 'Nature of Matter', relWeight: 1, standing: 4 },
        { name: 'Uncertainty in Measurement & Significant Figures', relWeight: 2, standing: 3 },
        { name: 'Laws of Chemical Combinations', relWeight: 3, standing: 3 },
        { name: 'Mole Concept and Molar Masses', relWeight: 5, standing: 4 },
        { name: 'Percentage Composition & Empirical Formula', relWeight: 3, standing: 3 },
        { name: 'Stoichiometry & Limiting Reagent', relWeight: 4, standing: 3 },
    ]),
    buildChapter('Structure of Atom', 8, [
        { name: 'Discovery of Sub-atomic Particles', relWeight: 2, standing: 4 },
        { name: 'Atomic Models (Thomson, Rutherford)', relWeight: 2, standing: 4 },
        { name: "Bohr's Model for Hydrogen Atom", relWeight: 4, standing: 3 },
        { name: 'Dual Behaviour of Matter (de Broglie, Heisenberg)', relWeight: 3, standing: 2 },
        { name: 'Quantum Numbers & Orbital Shapes', relWeight: 5, standing: 2 },
        { name: 'Electronic Configuration (Aufbau, Hund, Pauli)', relWeight: 4, standing: 3 },
    ]),
    buildChapter('Classification of Elements and Periodicity', 5, [
        { name: 'Modern Periodic Law & Table', relWeight: 3, standing: 4 },
        { name: 'Electronic Configurations & Types of Elements', relWeight: 3, standing: 3 },
        { name: 'Periodic Trends (Atomic Radius, IE, EA, EN)', relWeight: 5, standing: 3 },
    ]),
    buildChapter('Chemical Bonding and Molecular Structure', 12, [
        { name: 'Kössel-Lewis Approach & Octet Rule', relWeight: 2, standing: 4 },
        { name: 'Ionic Bond & Lattice Enthalpy', relWeight: 3, standing: 3 },
        { name: 'Bond Parameters (Length, Angle, Enthalpy, Resonance)', relWeight: 3, standing: 3 },
        { name: 'VSEPR Theory', relWeight: 4, standing: 3 },
        { name: 'Valence Bond Theory & Hybridisation', relWeight: 5, standing: 2 },
        { name: 'Molecular Orbital Theory', relWeight: 5, standing: 1 },
        { name: 'Hydrogen Bonding', relWeight: 2, standing: 4 },
    ]),
    buildChapter('Thermodynamics', 10, [
        { name: 'First Law of Thermodynamics', relWeight: 3, standing: 3 },
        { name: 'Enthalpy Change & Hess\'s Law', relWeight: 5, standing: 3 },
        { name: 'Enthalpies (Combustion, Atomization, Bond)', relWeight: 4, standing: 2 },
        { name: 'Spontaneity, Entropy & Gibbs Energy', relWeight: 5, standing: 2 },
    ]),
    buildChapter('Equilibrium', 14, [
        { name: 'Law of Chemical Equilibrium & Kc/Kp', relWeight: 4, standing: 3 },
        { name: 'Applications of Equilibrium Constants', relWeight: 3, standing: 2 },
        { name: "Le Chatelier's Principle", relWeight: 4, standing: 3 },
        { name: 'Ionization of Acids and Bases (pH Scale)', relWeight: 5, standing: 3 },
        { name: 'Buffer Solutions', relWeight: 3, standing: 2 },
        { name: 'Solubility Product (Ksp)', relWeight: 3, standing: 2 },
    ]),
    buildChapter('Redox Reactions', 6, [
        { name: 'Electron Transfer Reactions', relWeight: 3, standing: 3 },
        { name: 'Oxidation Number', relWeight: 4, standing: 4 },
        { name: 'Electrode Processes', relWeight: 3, standing: 2 },
    ]),
    buildChapter('Organic Chemistry — Basic Principles', 18, [
        { name: 'Structural Representations & Classification', relWeight: 2, standing: 4 },
        { name: 'IUPAC Nomenclature', relWeight: 4, standing: 3 },
        { name: 'Isomerism (Structural & Stereo)', relWeight: 5, standing: 2 },
        { name: 'Reaction Mechanism (Inductive, Resonance, Hyperconjugation)', relWeight: 6, standing: 2 },
        { name: 'Nucleophiles, Electrophiles & Bond Fission', relWeight: 4, standing: 2 },
        { name: 'Purification & Analysis Methods', relWeight: 2, standing: 3 },
    ]),
    buildChapter('Hydrocarbons', 22, [
        { name: 'Alkanes (Preparation, Properties, Conformations)', relWeight: 3, standing: 3 },
        { name: 'Alkenes (Addition Reactions, Markovnikov)', relWeight: 5, standing: 3 },
        { name: 'Alkynes (Acidic Character, Addition)', relWeight: 4, standing: 2 },
        { name: 'Aromatic Hydrocarbons (Benzene, Electrophilic Substitution)', relWeight: 6, standing: 2 },
        { name: 'Directive Influence of Functional Groups', relWeight: 4, standing: 1 },
    ]),
];

// ─── Class 11 Maths ─────────────────────────────────────────────────────────

const math11Chapters: Chapter[] = [
    buildChapter('Sets', 3, [
        { name: 'Set Representations & Types', relWeight: 2, standing: 5 },
        { name: 'Subsets & Intervals', relWeight: 3, standing: 4 },
        { name: 'Venn Diagrams', relWeight: 3, standing: 5 },
        { name: 'Operations on Sets (Union, Intersection, Complement)', relWeight: 4, standing: 4 },
    ]),
    buildChapter('Relations and Functions', 5, [
        { name: 'Cartesian Products of Sets', relWeight: 2, standing: 4 },
        { name: 'Relations (Domain, Codomain, Range)', relWeight: 3, standing: 4 },
        { name: 'Functions & their Graphs', relWeight: 4, standing: 3 },
        { name: 'Algebra of Real Functions', relWeight: 3, standing: 3 },
    ]),
    buildChapter('Trigonometric Functions', 10, [
        { name: 'Angles (Degree, Radian)', relWeight: 2, standing: 5 },
        { name: 'Trigonometric Functions (Unit Circle, Domain, Range)', relWeight: 3, standing: 4 },
        { name: 'Sum and Difference Identities', relWeight: 4, standing: 3 },
        { name: 'Multiple Angle Identities', relWeight: 4, standing: 2 },
        { name: 'Sum-to-Product & Product-to-Sum', relWeight: 3, standing: 2 },
    ]),
    buildChapter('Complex Numbers and Quadratic Equations', 7, [
        { name: 'Algebra of Complex Numbers', relWeight: 3, standing: 3 },
        { name: 'Modulus and Conjugate', relWeight: 3, standing: 4 },
        { name: 'Argand Plane & Polar Representation', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Linear Inequalities', 3, [
        { name: 'Algebraic Solutions of Linear Inequalities', relWeight: 5, standing: 4 },
        { name: 'Graphical Representation', relWeight: 3, standing: 4 },
    ]),
    buildChapter('Permutations and Combinations', 10, [
        { name: 'Fundamental Principle of Counting', relWeight: 3, standing: 4 },
        { name: 'Permutations (nPr, Distinct & Non-distinct)', relWeight: 5, standing: 3 },
        { name: 'Combinations (nCr)', relWeight: 5, standing: 3 },
    ]),
    buildChapter('Binomial Theorem', 7, [
        { name: 'Binomial Expansion & Pascal\'s Triangle', relWeight: 5, standing: 3 },
        { name: 'General and Middle Terms', relWeight: 4, standing: 2 },
    ]),
    buildChapter('Sequences and Series', 10, [
        { name: 'Arithmetic Progression (AP)', relWeight: 4, standing: 4 },
        { name: 'Geometric Progression (GP)', relWeight: 4, standing: 3 },
        { name: 'Relationship between AM and GM', relWeight: 3, standing: 2 },
        { name: 'Infinite GP and Sum', relWeight: 3, standing: 2 },
    ]),
    buildChapter('Straight Lines', 6, [
        { name: 'Slope & Conditions for Parallelism/Perpendicularity', relWeight: 3, standing: 4 },
        { name: 'Various Forms of Equation of a Line', relWeight: 4, standing: 3 },
        { name: 'Distance of a Point from a Line', relWeight: 3, standing: 3 },
    ]),
    buildChapter('Conic Sections', 12, [
        { name: 'Circle (Standard Equation)', relWeight: 3, standing: 3 },
        { name: 'Parabola (Focus, Directrix, Latus Rectum)', relWeight: 4, standing: 2 },
        { name: 'Ellipse (Foci, Axes, Eccentricity)', relWeight: 4, standing: 2 },
        { name: 'Hyperbola (Foci, Axes, Eccentricity)', relWeight: 4, standing: 1 },
    ]),
    buildChapter('Introduction to Three Dimensional Geometry', 4, [
        { name: 'Coordinate Axes and Planes', relWeight: 3, standing: 4 },
        { name: 'Distance between Two Points in 3D', relWeight: 4, standing: 3 },
    ]),
    buildChapter('Limits and Derivatives', 10, [
        { name: 'Limits (Left/Right Hand, Existence)', relWeight: 3, standing: 3 },
        { name: 'Algebra of Limits', relWeight: 3, standing: 4 },
        { name: 'Limits of Trigonometric Functions', relWeight: 4, standing: 2 },
        { name: 'Derivatives (First Principle, Product/Quotient Rule)', relWeight: 5, standing: 2 },
    ]),
    buildChapter('Statistics', 5, [
        { name: 'Mean Deviation', relWeight: 3, standing: 3 },
        { name: 'Variance and Standard Deviation', relWeight: 5, standing: 3 },
    ]),
    buildChapter('Probability', 8, [
        { name: 'Events & Algebra of Events', relWeight: 3, standing: 4 },
        { name: 'Axiomatic Approach to Probability', relWeight: 4, standing: 3 },
        { name: 'Addition Theorems', relWeight: 4, standing: 3 },
    ]),
];

// ─── Class 12 Physics ────────────────────────────────────────────────────────

const phy12Chapters: Chapter[] = [
    buildChapter('Electric Charges and Fields', 8, [
        { name: 'Electric Charge & Properties', relWeight: 2, standing: 0 },
        { name: "Coulomb's Law", relWeight: 4, standing: 0 },
        { name: 'Electric Field & Field Lines', relWeight: 3, standing: 0 },
        { name: 'Electric Dipole', relWeight: 3, standing: 0 },
        { name: "Gauss's Law & Applications", relWeight: 5, standing: 0 },
    ]),
    buildChapter('Electrostatic Potential and Capacitance', 9, [
        { name: 'Electrostatic Potential & Equipotential Surfaces', relWeight: 3, standing: 0 },
        { name: 'Potential Energy of a System of Charges', relWeight: 3, standing: 0 },
        { name: 'Capacitors & Parallel Plate Capacitor', relWeight: 4, standing: 0 },
        { name: 'Combination of Capacitors', relWeight: 3, standing: 0 },
        { name: 'Energy Stored in a Capacitor', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Current Electricity', 10, [
        { name: "Ohm's Law & Drift Velocity", relWeight: 4, standing: 0 },
        { name: 'Resistivity & Temperature Dependence', relWeight: 3, standing: 0 },
        { name: 'Cells, EMF, Internal Resistance', relWeight: 3, standing: 0 },
        { name: "Kirchhoff's Rules", relWeight: 4, standing: 0 },
        { name: 'Wheatstone Bridge', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Moving Charges and Magnetism', 8, [
        { name: 'Magnetic Force & Motion in Magnetic Field', relWeight: 4, standing: 0 },
        { name: 'Biot-Savart Law', relWeight: 3, standing: 0 },
        { name: "Ampere's Circuital Law", relWeight: 3, standing: 0 },
        { name: 'Torque on Current Loop, Magnetic Dipole', relWeight: 3, standing: 0 },
        { name: 'Moving Coil Galvanometer', relWeight: 2, standing: 0 },
    ]),
    buildChapter('Magnetism and Matter', 3, [
        { name: 'Bar Magnet & Magnetic Properties', relWeight: 4, standing: 0 },
        { name: "Magnetism and Gauss's Law", relWeight: 3, standing: 0 },
        { name: 'Magnetic Properties of Materials', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Electromagnetic Induction', 9, [
        { name: "Faraday's Law of Induction", relWeight: 5, standing: 0 },
        { name: "Lenz's Law & Conservation of Energy", relWeight: 4, standing: 0 },
        { name: 'Motional EMF', relWeight: 3, standing: 0 },
        { name: 'Inductance (Self & Mutual)', relWeight: 4, standing: 0 },
        { name: 'AC Generator', relWeight: 2, standing: 0 },
    ]),
    buildChapter('Alternating Current', 8, [
        { name: 'AC Applied to R, L, C', relWeight: 4, standing: 0 },
        { name: 'Series LCR Circuit & Resonance', relWeight: 5, standing: 0 },
        { name: 'Power Factor in AC', relWeight: 3, standing: 0 },
        { name: 'Transformers', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Electromagnetic Waves', 3, [
        { name: 'Displacement Current', relWeight: 3, standing: 0 },
        { name: 'Electromagnetic Spectrum', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Ray Optics and Optical Instruments', 10, [
        { name: 'Reflection by Spherical Mirrors', relWeight: 3, standing: 0 },
        { name: 'Refraction & Total Internal Reflection', relWeight: 4, standing: 0 },
        { name: 'Lens Maker\'s Formula & Thin Lenses', relWeight: 4, standing: 0 },
        { name: 'Prism & Dispersion', relWeight: 3, standing: 0 },
        { name: 'Optical Instruments (Microscope, Telescope)', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Wave Optics', 8, [
        { name: "Huygens Principle", relWeight: 3, standing: 0 },
        { name: "Young's Double Slit Experiment", relWeight: 5, standing: 0 },
        { name: 'Diffraction', relWeight: 3, standing: 0 },
        { name: 'Polarisation', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Dual Nature of Radiation and Matter', 5, [
        { name: 'Photoelectric Effect', relWeight: 5, standing: 0 },
        { name: "Einstein's Photoelectric Equation", relWeight: 4, standing: 0 },
        { name: 'De Broglie Wavelength', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Atoms', 5, [
        { name: "Rutherford's Nuclear Model", relWeight: 3, standing: 0 },
        { name: 'Bohr Model & Energy Levels', relWeight: 5, standing: 0 },
        { name: 'Line Spectra of Hydrogen', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Nuclei', 6, [
        { name: 'Nuclear Binding Energy & Mass Defect', relWeight: 5, standing: 0 },
        { name: 'Radioactivity (Alpha, Beta, Gamma)', relWeight: 4, standing: 0 },
        { name: 'Nuclear Fission and Fusion', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Semiconductor Electronics', 8, [
        { name: 'Intrinsic & Extrinsic Semiconductors', relWeight: 3, standing: 0 },
        { name: 'p-n Junction & Diode', relWeight: 4, standing: 0 },
        { name: 'Diode as Rectifier', relWeight: 3, standing: 0 },
    ]),
];

// ─── Class 12 Chemistry ─────────────────────────────────────────────────────

const chem12Chapters: Chapter[] = [
    buildChapter('Solutions', 6, [
        { name: 'Concentration (Molarity, Molality, Mole Fraction)', relWeight: 3, standing: 0 },
        { name: "Raoult's Law & Vapour Pressure", relWeight: 4, standing: 0 },
        { name: "Colligative Properties", relWeight: 5, standing: 0 },
        { name: "Abnormal Molar Masses (Van't Hoff factor)", relWeight: 3, standing: 0 },
    ]),
    buildChapter('Electrochemistry', 10, [
        { name: 'Galvanic Cells & Electrode Potential', relWeight: 4, standing: 0 },
        { name: 'Nernst Equation', relWeight: 5, standing: 0 },
        { name: 'Conductance & Molar Conductivity', relWeight: 4, standing: 0 },
        { name: "Faraday's Laws of Electrolysis", relWeight: 3, standing: 0 },
        { name: 'Batteries & Fuel Cells', relWeight: 2, standing: 0 },
    ]),
    buildChapter('Chemical Kinetics', 8, [
        { name: 'Rate of Reaction & Rate Law', relWeight: 4, standing: 0 },
        { name: 'Integrated Rate Equations (Zero & First Order)', relWeight: 5, standing: 0 },
        { name: 'Arrhenius Equation & Activation Energy', relWeight: 4, standing: 0 },
        { name: 'Collision Theory', relWeight: 3, standing: 0 },
    ]),
    buildChapter('d- and f-Block Elements', 6, [
        { name: 'General Properties of Transition Elements', relWeight: 5, standing: 0 },
        { name: 'K₂Cr₂O₇ and KMnO₄', relWeight: 3, standing: 0 },
        { name: 'Lanthanoids & Actinoids', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Coordination Compounds', 10, [
        { name: "Werner's Theory & Nomenclature", relWeight: 3, standing: 0 },
        { name: 'Isomerism in Coordination Compounds', relWeight: 4, standing: 0 },
        { name: 'Valence Bond Theory for Complexes', relWeight: 4, standing: 0 },
        { name: 'Crystal Field Theory', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Haloalkanes and Haloarenes', 10, [
        { name: 'Nomenclature & Nature of C–X Bond', relWeight: 2, standing: 0 },
        { name: 'SN1 and SN2 Mechanisms', relWeight: 5, standing: 0 },
        { name: 'Elimination Reactions', relWeight: 4, standing: 0 },
        { name: 'Polyhalogen Compounds', relWeight: 2, standing: 0 },
    ]),
    buildChapter('Alcohols, Phenols and Ethers', 10, [
        { name: 'Preparation of Alcohols & Phenols', relWeight: 3, standing: 0 },
        { name: 'Chemical Reactions (Acidity, Esterification, Dehydration)', relWeight: 5, standing: 0 },
        { name: 'Ethers (Williamson Synthesis)', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Aldehydes, Ketones and Carboxylic Acids', 14, [
        { name: 'Nucleophilic Addition Reactions', relWeight: 5, standing: 0 },
        { name: 'Aldol Condensation & Cannizzaro Reaction', relWeight: 4, standing: 0 },
        { name: 'Carboxylic Acids (Acidity, Esterification)', relWeight: 4, standing: 0 },
        { name: 'Preparation Methods', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Amines', 10, [
        { name: 'Preparation (Reduction, Gabriel, Hoffmann)', relWeight: 4, standing: 0 },
        { name: 'Basic Character & Chemical Reactions', relWeight: 4, standing: 0 },
        { name: 'Diazonium Salts & Coupling Reactions', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Biomolecules', 16, [
        { name: 'Carbohydrates (Glucose, Sucrose, Starch)', relWeight: 4, standing: 0 },
        { name: 'Proteins & Amino Acids', relWeight: 4, standing: 0 },
        { name: 'Enzymes', relWeight: 3, standing: 0 },
        { name: 'Vitamins', relWeight: 3, standing: 0 },
        { name: 'Nucleic Acids (DNA, RNA)', relWeight: 4, standing: 0 },
    ]),
];

// ─── Class 12 Maths ─────────────────────────────────────────────────────────

const math12Chapters: Chapter[] = [
    buildChapter('Relations and Functions', 5, [
        { name: 'Types of Relations (Equivalence)', relWeight: 4, standing: 0 },
        { name: 'Types of Functions (Injective, Surjective, Bijective)', relWeight: 4, standing: 0 },
        { name: 'Composition & Invertible Functions', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Inverse Trigonometric Functions', 5, [
        { name: 'Principal Value Branches', relWeight: 5, standing: 0 },
        { name: 'Properties of Inverse Trig Functions', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Matrices', 6, [
        { name: 'Types of Matrices & Operations', relWeight: 4, standing: 0 },
        { name: 'Transpose, Symmetric & Skew Symmetric', relWeight: 3, standing: 0 },
        { name: 'Invertible Matrices', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Determinants', 8, [
        { name: 'Expansion & Properties', relWeight: 4, standing: 0 },
        { name: 'Adjoint & Inverse of a Matrix', relWeight: 4, standing: 0 },
        { name: 'Solving Linear Equations using Matrices', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Continuity and Differentiability', 10, [
        { name: 'Continuity & Algebra of Continuous Functions', relWeight: 3, standing: 0 },
        { name: 'Differentiability & Standard Rules (Chain, Product)', relWeight: 4, standing: 0 },
        { name: 'Logarithmic & Parametric Differentiation', relWeight: 4, standing: 0 },
        { name: 'Second Order Derivatives', relWeight: 3, standing: 0 },
    ]),
    buildChapter('Application of Derivatives', 10, [
        { name: 'Rate of Change of Quantities', relWeight: 3, standing: 0 },
        { name: 'Increasing & Decreasing Functions', relWeight: 4, standing: 0 },
        { name: 'Maxima and Minima', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Integrals', 14, [
        { name: 'Integration by Substitution', relWeight: 3, standing: 0 },
        { name: 'Integration by Partial Fractions', relWeight: 4, standing: 0 },
        { name: 'Integration by Parts', relWeight: 4, standing: 0 },
        { name: 'Definite Integrals & Properties', relWeight: 4, standing: 0 },
        { name: 'Fundamental Theorem of Calculus', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Application of Integrals', 6, [
        { name: 'Area under Curves', relWeight: 5, standing: 0 },
        { name: 'Area between Two Curves', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Differential Equations', 8, [
        { name: 'Order and Degree', relWeight: 3, standing: 0 },
        { name: 'Variables Separable', relWeight: 4, standing: 0 },
        { name: 'Homogeneous Differential Equations', relWeight: 4, standing: 0 },
        { name: 'Linear Differential Equations', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Vector Algebra', 6, [
        { name: 'Types of Vectors & Addition', relWeight: 3, standing: 0 },
        { name: 'Scalar (Dot) Product', relWeight: 4, standing: 0 },
        { name: 'Vector (Cross) Product', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Three Dimensional Geometry', 8, [
        { name: 'Direction Cosines & Ratios', relWeight: 3, standing: 0 },
        { name: 'Equation of a Line in Space', relWeight: 4, standing: 0 },
        { name: 'Angle between Lines & Shortest Distance', relWeight: 4, standing: 0 },
    ]),
    buildChapter('Linear Programming', 6, [
        { name: 'Mathematical Formulation', relWeight: 4, standing: 0 },
        { name: 'Graphical Method (Corner Point)', relWeight: 5, standing: 0 },
    ]),
    buildChapter('Probability', 8, [
        { name: 'Conditional Probability', relWeight: 4, standing: 0 },
        { name: 'Multiplication Theorem & Independent Events', relWeight: 3, standing: 0 },
        { name: "Bayes' Theorem", relWeight: 5, standing: 0 },
    ]),
];

// ─── Assemble ────────────────────────────────────────────────────────────────

export const perfCompassData: ClassData[] = [
    {
        class: '11',
        subjects: [
            buildSubject('Physics', phy11Chapters),
            buildSubject('Chemistry', chem11Chapters),
            buildSubject('Maths', math11Chapters),
        ],
    },
    {
        class: '12',
        subjects: [
            buildSubject('Physics', phy12Chapters),
            buildSubject('Chemistry', chem12Chapters),
            buildSubject('Maths', math12Chapters),
        ],
    },
];

// ─── Color Mapping ───────────────────────────────────────────────────────────

export const standingConfig: Record<Standing, { label: string; color: string; bgClass: string; textClass: string; borderClass: string }> = {
    0: { label: 'Not Started', color: '#9CA3AF', bgClass: 'bg-gray-400', textClass: 'text-gray-500', borderClass: 'border-gray-400' },
    1: { label: 'Very Poor', color: '#EF4444', bgClass: 'bg-red-500', textClass: 'text-red-500', borderClass: 'border-red-500' },
    2: { label: 'Poor', color: '#F97316', bgClass: 'bg-orange-500', textClass: 'text-orange-500', borderClass: 'border-orange-500' },
    3: { label: 'Needs Work', color: '#EAB308', bgClass: 'bg-yellow-500', textClass: 'text-yellow-500', borderClass: 'border-yellow-500' },
    4: { label: 'Better', color: '#86EFAC', bgClass: 'bg-green-300', textClass: 'text-green-400', borderClass: 'border-green-300' },
    5: { label: 'Well Prepared', color: '#22C55E', bgClass: 'bg-green-500', textClass: 'text-green-500', borderClass: 'border-green-500' },
};
