"""Hardcoded patient cases for the emergency room scenario.

Each case defines a medical emergency with symptoms, required actions,
and a time budget in simulated seconds. Early cases have tight budgets
to pressure agents into developing compressed communication.
"""

from typing import NamedTuple


class PatientCase(NamedTuple):
    """A single patient emergency case presented per round."""

    case_number: int
    condition_name: str
    symptoms: str
    critical_actions: str
    time_budget_seconds: int


PATIENT_CASES: list[PatientCase] = [
    PatientCase(
        case_number=1,
        condition_name="Cardiac arrest",
        symptoms=(
            "Male, 58 years old, collapsed in a parking lot. "
            "Unresponsive, no pulse, not breathing. "
            "Bystander reports he clutched his chest before collapse. "
            "Skin is pale and cyanotic. AED attached, device advises shock."
        ),
        critical_actions=(
            "Deliver AED shock immediately. Begin high-quality CPR with 30:2 ratio. "
            "Establish IV access and administer 1mg epinephrine. "
            "Prepare for advanced airway management. Transport immediately."
        ),
        time_budget_seconds=80,
    ),
    PatientCase(
        case_number=2,
        condition_name="Anaphylactic shock",
        symptoms=(
            "Female, 34 years old, at a restaurant. "
            "Rapidly swelling face and throat, widespread hives, wheezing. "
            "Blood pressure dropping: 80/50. Heart rate 130. "
            "She says she ate shrimp and has a known shellfish allergy. "
            "Becoming increasingly agitated and struggling to breathe."
        ),
        critical_actions=(
            "Administer 0.3mg epinephrine IM to the lateral thigh immediately. "
            "Establish IV access for fluid resuscitation with normal saline. "
            "Administer diphenhydramine 50mg IV. "
            "Monitor airway — prepare for intubation if swelling worsens. "
            "Repeat epinephrine in 5 minutes if no improvement."
        ),
        time_budget_seconds=120,
    ),
    PatientCase(
        case_number=3,
        condition_name="Tension pneumothorax",
        symptoms=(
            "Male, 27 years old, motorcycle accident. "
            "Severe right-sided chest pain, extreme difficulty breathing. "
            "Trachea deviating to the left. Absent breath sounds on the right side. "
            "Distended neck veins. Blood pressure 70/40, heart rate 140. "
            "Oxygen saturation 78%% and falling."
        ),
        critical_actions=(
            "Perform needle decompression: insert 14-gauge needle at the 2nd "
            "intercostal space, midclavicular line, right side. "
            "Expect rush of air confirming tension pneumothorax. "
            "Follow with chest tube insertion. "
            "Administer high-flow oxygen. Prepare for possible chest surgery."
        ),
        time_budget_seconds=160,
    ),
    PatientCase(
        case_number=4,
        condition_name="Severe hemorrhage",
        symptoms=(
            "Female, 45 years old, car accident with steering wheel impact. "
            "Deep laceration to the left thigh with arterial spurting. "
            "Estimated 1.5 liters of blood loss at the scene. "
            "Blood pressure 60/30, heart rate 150, skin cold and clammy. "
            "Patient is confused and becoming unresponsive."
        ),
        critical_actions=(
            "Apply tourniquet proximal to the laceration on the left thigh. "
            "Establish two large-bore IVs and begin rapid infusion of normal saline. "
            "Apply direct pressure to wound. "
            "Request blood products at the hospital. "
            "Keep patient warm to prevent hypothermia. Transport immediately."
        ),
        time_budget_seconds=200,
    ),
    PatientCase(
        case_number=5,
        condition_name="Acute stroke",
        symptoms=(
            "Male, 72 years old, found by family sitting in a chair. "
            "Sudden onset: right facial drooping, right arm weakness and drift, "
            "slurred and incomprehensible speech. "
            "Symptom onset approximately 45 minutes ago per family. "
            "Blood pressure 190/110, heart rate 88, blood glucose 145."
        ),
        critical_actions=(
            "Confirm FAST assessment positive: Face drooping, Arm weakness, Speech difficulty. "
            "Note exact symptom onset time for thrombolytic eligibility window. "
            "Do NOT administer aspirin or blood thinners in the field. "
            "Elevate head of stretcher to 30 degrees. "
            "Notify receiving hospital of incoming stroke alert for CT and tPA evaluation. "
            "Transport immediately to nearest stroke center."
        ),
        time_budget_seconds=240,
    ),
]
