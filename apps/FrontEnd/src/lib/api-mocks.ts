export const UserProfile = {
    name: "Visu",
    class: "11",
    board: "CBSE",
    email: "test@test.com",
    goal: "JEE"
};

export interface Chapter {
    id: number;
    class: number;
    subject: string;
    chapterNumber: number;
    title: string;
    pdfUrl: string;
    board: string;
}

export const ChapterData: Chapter[] = [
    { id: 15, class: 11, subject: "Physics", chapterNumber: 1, title: "Units and Measurement", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph101.pdf", board: "CBSE" },
    { id: 16, class: 11, subject: "Physics", chapterNumber: 2, title: "Motion in a Straight Line", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph102.pdf", board: "CBSE" },
    { id: 17, class: 11, subject: "Physics", chapterNumber: 3, title: "Motion in a Plane", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph103.pdf", board: "CBSE" },
    { id: 18, class: 11, subject: "Physics", chapterNumber: 4, title: "Laws of Motion", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph104.pdf", board: "CBSE" },
    { id: 19, class: 11, subject: "Physics", chapterNumber: 5, title: "Work, Energy and Power", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph105.pdf", board: "CBSE" },
    { id: 20, class: 11, subject: "Physics", chapterNumber: 6, title: "Systems of Particles and Rotational Motion", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph106.pdf", board: "CBSE" },
    { id: 21, class: 11, subject: "Physics", chapterNumber: 7, title: "Gravitation", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph107.pdf", board: "CBSE" },
    { id: 22, class: 11, subject: "Physics", chapterNumber: 8, title: "Mechanical Properties of Solids", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph201.pdf", board: "CBSE" },
    { id: 23, class: 11, subject: "Physics", chapterNumber: 9, title: "Mechanical Properties of Fluids", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph202.pdf", board: "CBSE" },
    { id: 24, class: 11, subject: "Physics", chapterNumber: 10, title: "Thermal Properties of Matter", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph203.pdf", board: "CBSE" },
    { id: 25, class: 11, subject: "Physics", chapterNumber: 11, title: "Thermodynamics", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph204.pdf", board: "CBSE" },
    { id: 26, class: 11, subject: "Physics", chapterNumber: 12, title: "Kinetic Theory", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph205.pdf", board: "CBSE" },
    { id: 27, class: 11, subject: "Physics", chapterNumber: 13, title: "Oscillations", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph206.pdf", board: "CBSE" },
    { id: 28, class: 11, subject: "Physics", chapterNumber: 14, title: "Waves", pdfUrl: "https://<YOUR_STORAGE>.blob.core.windows.net/Feedback/11/Physics/keph207.pdf", board: "CBSE" },
];

export const SampleQuestion = {
    "has_figure": true,
    "figure_info": [{
        "url": "https://<YOUR_STORAGE>.blob.core.windows.net/onlineresources/questions/11/Physics/ch_11/figure_11_8.png",
        "type": "GRAPH",
        "local_path": "",
        "description": "A P-V diagram showing a thermodynamic cycle involving points D, E, and F."
    }],
    "page_number": 18,
    "visual_data": {
        "type": "GRAPH",
        "box_2d": [88, 130, 440, 830],
        "description": "A P-V diagram showing a thermodynamic cycle involving points D, E, and F.",
        "visual_source": "current_page",
        "cropped_image_path": "cropped_images\\keph204\\q11_8_fig.png"
    },
    "question_text": "A thermodynamic system is taken from an original state to an intermediate state by the linear process shown in Fig. (11.13)\n\nIts volume is then reduced to the original value from E to F by an isobaric process. Calculate the total work done by the gas from D to E to F",
    "figure_references": ["Fig. 11.11"]
};

export const SampleSolution = {
    "steps": [
        {
            "step_type": "conceptual",
            "nudge_hint": "Hint: Calculate the area under the trapezoid.",
            "explanation": "**Given:**\n*   Initial state D: $P_D = 600 \\text{ N/m}^2$, $V_D = 2.0 \\text{ m}^3$.\n*   Intermediate state E: $P_E = 300 \\text{ N/m}^2$, $V_E = 5.0 \\text{ m}^3$.\n*   Final state F: $V_F = V_D = 2.0 \\text{ m}^3$. The process E $\\to$ F is isobaric, so $P_F = P_E = 300 \\text{ N/m}^2$.\n\n**To find:** Total work done $W_{total} = W_{DE} + W_{EF}$.\n\n**Governing Principle:** Work done by a gas is the area under the curve in a P-V diagram, $W = \\int P dV$.",
            "step_number": 1,
            "latex_formula": "W_{DE} = \\text{Area of Trapezoid} = \\frac{1}{2} (P_D + P_E) (V_E - V_D)"
        },
        {
            "step_type": "calculation",
            "nudge_hint": "Hint: Think about volume change direction...",
            "explanation": "The process D $\\to$ E is a linear expansion. The work done $W_{DE}$ is the area of the trapezoid under the line segment DE.\n\nArea of trapezoid = $\\frac{1}{2} \\times (\\text{sum of parallel sides}) \\times (\\text{height})$\n$W_{DE} = \\frac{1}{2} (P_D + P_E) (V_E - V_D)$\n$W_{DE} = \\frac{1}{2} (600 + 300 \\text{ N/m}^2) (5.0 - 2.0 \\text{ m}^3)$\n$W_{DE} = \\frac{1}{2} (900) (3.0) = 1350 \\text{ J}$.\nSince the volume increases, the work done by the gas is positive.",
            "step_number": 2,
            "latex_formula": "W_{EF} = P \\Delta V = P_E (V_F - V_E)"
        },
        {
            "step_type": "calculation",
            "nudge_hint": "Hint: Sum the work from all individual steps.",
            "explanation": "The process E $\\to$ F is an isobaric (constant pressure) compression. The work done is:\n$W_{EF} = P \\Delta V = P_E (V_F - V_E)$\n$W_{EF} = 300 \\text{ N/m}^2 (2.0 - 5.0 \\text{ m}^3)$\n$W_{EF} = 300 (-3.0) = -900 \\text{ J}$.\nSince the volume decreases, the work done by the gas is negative.",
            "step_number": 3,
            "latex_formula": "W_{total} = W_{DE} + W_{EF}"
        },
        {
            "step_type": "calculation",
            "nudge_hint": "Hint: What is the net work done?",
            "explanation": "The total work done by the gas is the sum of the work done in each step:\n$W_{total} = W_{DE} + W_{EF}$\n$W_{total} = 1350 \\text{ J} + (-900 \\text{ J}) = 450 \\text{ J}$.\n\n*Alternatively*, the total work done in the cycle D-E-F-D is the area enclosed by the triangle DEF. Since the cycle D $\\to$ E $\\to$ F is clockwise, the net work is positive.\nArea = $\\frac{1}{2} \\times \\text{base} \\times \\text{height} = \\frac{1}{2} (V_E - V_F)(P_D - P_F)$\nArea = $\\frac{1}{2} (5.0 - 2.0)(600 - 300) = \\frac{1}{2} (3.0)(300) = 450 \\text{ J}$.",
            "step_number": 4,
            "latex_formula": "W_{total} = 450 \\text{ J}"
        }
    ],
    "question_id": "11.8",
    "final_answer": "The total work done by the gas is $\\mathbf{450 \\text{ J}}$.",
    "question_text": "A thermodynamic system is taken from an original state to an intermediate state by the linear process shown in Fig. (11.13)\n\n[Image of P-V diagram showing path D to E]\n\nIts volume is then reduced to the original value from E to F by an isobaric process. Calculate the total work done by the gas from D to E to F",
    "rendered_text": "..."
};

// Feedback Interfaces
export interface FeedbackStep {
    step_number: number;
    description: string;
    calculation: string;
}

export interface FullSolution {
    title: string;
    steps: FeedbackStep[];
}

export interface FeedbackDetails {
    conceptual_understanding: string;
    calculation_errors: string;
    presentation_and_steps: string;
}

export interface StudentFeedback {
    tip: string;
}

export interface SolutionFeedbackData {
    chapter_name: string;
    evaluation_status: string;
    evaluation_details: FeedbackDetails;
    feedback_for_student: StudentFeedback;
    full_solution: FullSolution;
}

export const SAMPLE_FEEDBACK_DATA: SolutionFeedbackData = {
    "chapter_name": "Thermodynamics",
    "evaluation_status": "Answer is Acceptable",
    "evaluation_details": {
        "conceptual_understanding": "The student demonstrates excellent conceptual understanding. They correctly identified Nitrogen ($N_2$) as a diatomic gas and selected the correct specific heat capacity at constant pressure ($C_p = \\frac{7}{2}R$). The formula for heat at constant pressure ($Q = \\mu C_p \\Delta T$) was also applied correctly.",
        "calculation_errors": "There is a minor precision error due to early rounding. The student calculated the number of moles as $0.71$ (decimal approximation) rather than keeping it as the fraction $\\frac{5}{7}$. This caused the final answer to be $928.14 \\text{ J}$ instead of the precise $933.75 \\text{ J}$.",
        "presentation_and_steps": "The work is presented clearly. The data ($\\Delta T, m, C_p, R$) is listed explicitly, and the substitution into the formula is easy to follow. The unit notation $^\\circ K$ for Kelvin is technically incorrect (should just be K), but the numerical value used was correct."
    },
    "feedback_for_student": {
        "tip": "Great job correctly determining that $C_p = \\frac{7}{2}R$ for a diatomic gas! Your physics concepts are spot on. A quick tip for math: Try to keep values as fractions (like moles = $\\frac{20}{28} = \\frac{5}{7}$) instead of rounding to decimals ($0.71$). If you had kept the fraction, the '7' from the moles would have cancelled out perfectly with the '7' in $\\frac{7}{2}R$, making the calculation easier and the answer exact!"
    },
    "full_solution": {
        "title": "Heat Supplied at Constant Pressure",
        "steps": [
            {
                "step_number": 1,
                "description": "Identify the given values and convert units.",
                "calculation": "$$m = 2.0 \\times 10^{-2} \\text{ kg} = 20 \\text{ g}$$\n$$\\Delta T = 45^\\circ \\text{C} = 45 \\text{ K}$$\n$$M = 28 \\text{ g/mol}$$\n$$R = 8.3 \\text{ J mol}^{-1} \\text{K}^{-1}$$"
            },
            {
                "step_number": 2,
                "description": "Calculate the number of moles ($\\mu$).",
                "calculation": "$$\\mu = \\frac{\\text{mass}}{\\text{Molar Mass}} = \\frac{20}{28} = \\frac{5}{7} \\text{ mol}$$"
            },
            {
                "step_number": 3,
                "description": "Determine the Molar Specific Heat at Constant Pressure ($C_p$) for Nitrogen (Diatomic gas).",
                "calculation": "For a diatomic gas,\n$$C_p = \\frac{7}{2}R$$"
            },
            {
                "step_number": 4,
                "description": "Calculate the heat supplied ($Q$) using the formula $Q = \\mu C_p \\Delta T$.",
                "calculation": "$$Q = \\left( \\frac{5}{7} \\right) \\times \\left( \\frac{7}{2} R \\right) \\times 45$$\n$$Q = \\left( \\frac{5}{7} \\right) \\times \\left( \\frac{7}{2} \\times 8.3 \\right) \\times 45$$\nNotice the 7s cancel out:\n$$Q = \\frac{5}{2} \\times 8.3 \\times 45$$\n$$Q = 2.5 \\times 373.5$$\n$$Q = 933.75 \\text{ J}$$"
            },
            {
                "step_number": 5,
                "description": "Final Answer.",
                "calculation": "$$Q \\approx 934 \\text{ J}$$"
            }
        ]
    }
};
