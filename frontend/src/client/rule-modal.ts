// Client wiring for the /preferences rule modal: add, edit and onboarding
// states, the daily/weekly sections, the ward picker, and form validation.
import type { StarterRule } from "../lib/onboarding";
import { findRuleFormError } from "../lib/rule-form";

export function initRuleModal(): void {
  const modal = document.getElementById("ruleModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalSubtitle = document.getElementById("modalSubtitle");
  const defaultModalSubtitle = modalSubtitle?.textContent ?? "";
  const ruleForm = document.getElementById("ruleForm") as HTMLFormElement;
  const ruleIdInput = document.getElementById("ruleId") as HTMLInputElement;
  const ruleNameInput = document.getElementById("ruleName") as HTMLInputElement;
  const searchTermInput = document.getElementById("searchTerm") as HTMLInputElement;
  const isActiveInput = document.getElementById("isActive") as HTMLInputElement;
  const notificationTypeRadios = document.querySelectorAll<HTMLInputElement>('input[name="notification_type"]');
  const dailyOptionsSection = document.getElementById("dailyOptionsSection");
  const weeklyOptionsSection = document.getElementById("weeklyOptionsSection");
  const wardFilterSection = document.getElementById("wardFilterSection");
  const cancelBtn = document.getElementById("cancelBtn");
  const addRuleBtns = document.querySelectorAll("#addRuleBtn, #addRuleBtn2");
  const editRuleBtns = document.querySelectorAll(".edit-rule-btn");
  const toggleWardsBtn = document.getElementById("toggleWardsBtn");
  const wardSelectionContainer = document.getElementById("wardSelectionContainer");

  // Toggle Ward Section
  toggleWardsBtn?.addEventListener("click", () => {
    const isHidden = wardSelectionContainer?.classList.contains("hidden");
    if (isHidden) {
      wardSelectionContainer?.classList.remove("hidden");
      toggleWardsBtn.textContent = "Hide Wards";
    } else {
      wardSelectionContainer?.classList.add("hidden");
      toggleWardsBtn.textContent = "Show Wards";
    }
  });

  /** The hidden delivery_frequency field, added to the form on first use. */
  function setDeliveryFrequency(frequency: "daily" | "weekly"): void {
    let frequencyInput = document.getElementById("hidden_frequency") as HTMLInputElement | null;
    if (!frequencyInput) {
      frequencyInput = document.createElement("input");
      frequencyInput.type = "hidden";
      frequencyInput.name = "delivery_frequency";
      frequencyInput.id = "hidden_frequency";
      ruleForm.appendChild(frequencyInput);
    }
    frequencyInput.value = frequency;
  }

  /** Check `to`'s topics that were checked in `from`, then clear `from` so topics aren't submitted twice. */
  function moveTopicSelection(from: NodeListOf<HTMLInputElement> | undefined, to: NodeListOf<HTMLInputElement> | undefined): void {
    const checkedTopics = Array.from(from ?? [])
      .filter((cb) => cb.checked)
      .map((cb) => cb.value);
    to?.forEach((cb) => {
      cb.checked = checkedTopics.includes(cb.value);
    });
    from?.forEach((cb) => (cb.checked = false));
  }

  // Toggle sections based on notification type
  function toggleNotificationTypeSections(): void {
    const selectedType = document.querySelector<HTMLInputElement>('input[name="notification_type"]:checked');
    const wardCheckboxes = document.querySelectorAll<HTMLInputElement>('input[name="wards"]');

    // Get topic checkboxes from both sections
    const dailyTopicCheckboxes = dailyOptionsSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]');
    const weeklyTopicCheckboxes = weeklyOptionsSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]');

    if (selectedType && selectedType.value === "weekly") {
      moveTopicSelection(dailyTopicCheckboxes, weeklyTopicCheckboxes);

      // Show weekly options, hide daily options and ward filter
      dailyOptionsSection?.classList.add("hidden");
      weeklyOptionsSection?.classList.remove("hidden");
      wardFilterSection?.classList.add("hidden");

      // Clear ward selections
      wardCheckboxes.forEach((cb) => (cb.checked = false));
      wardSelectionContainer?.classList.add("hidden");
      if (toggleWardsBtn) toggleWardsBtn.textContent = "Show Wards";

      setDeliveryFrequency("weekly");
    } else {
      moveTopicSelection(weeklyTopicCheckboxes, dailyTopicCheckboxes);

      // Show daily options, hide weekly options, show ward filter
      dailyOptionsSection?.classList.remove("hidden");
      weeklyOptionsSection?.classList.add("hidden");
      wardFilterSection?.classList.remove("hidden");

      setDeliveryFrequency("daily");
    }
  }

  notificationTypeRadios.forEach((radio) => {
    radio.addEventListener("change", toggleNotificationTypeSections);
  });

  // Initialize on page load
  toggleNotificationTypeSections();

  // Open modal for a new rule, reset to the default (daily) state
  function openNewRuleModal(): void {
    modalTitle!.textContent = "Add Notification Rule";
    if (modalSubtitle) modalSubtitle.textContent = defaultModalSubtitle;
    ruleForm.action = "/api/notifications/create-rule";
    ruleForm.reset();
    ruleIdInput.value = "";
    searchTermInput.value = "";

    // Reset to default (daily)
    notificationTypeRadios[0].checked = true;

    // Reset wards UI
    wardSelectionContainer?.classList.add("hidden");
    if (toggleWardsBtn) toggleWardsBtn.textContent = "Show Wards";

    toggleNotificationTypeSections();
    modal?.classList.remove("hidden");
  }

  addRuleBtns.forEach((btn) => {
    btn?.addEventListener("click", openNewRuleModal);
  });

  // Onboarding: open the new-rule modal in its starter state
  function openStarterRuleModal(starterRule: StarterRule): void {
    openNewRuleModal();
    modalTitle!.textContent = "Create Your First Alert";
    if (modalSubtitle) {
      modalSubtitle.textContent = "You'll only receive emails once you save an alert. Pick the topics you care about.";
    }
    ruleNameInput.value = starterRule.name;

    notificationTypeRadios.forEach((radio) => {
      radio.checked = radio.value === starterRule.deliveryFrequency;
    });
    toggleNotificationTypeSections();
  }

  const starterRuleData = modal?.dataset.starterRule;
  if (starterRuleData) {
    openStarterRuleModal(JSON.parse(starterRuleData) as StarterRule);
  }

  // Open modal for editing rule
  editRuleBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const target = e.currentTarget as HTMLButtonElement;
      const ruleId = target.dataset.ruleId;
      const ruleName = target.dataset.ruleName;
      const ruleTopics = JSON.parse(target.dataset.ruleTopics || "[]") as string[];
      const ruleWards = JSON.parse(target.dataset.ruleWardNumbers || "[]") as string[];
      const ruleSearchTerm = target.dataset.ruleSearchTerm;
      const ruleFrequency = target.dataset.ruleDeliveryFrequency || "daily";
      const ruleActive = target.dataset.ruleActive === "true";

      modalTitle!.textContent = "Edit Notification Rule";
      if (modalSubtitle) modalSubtitle.textContent = defaultModalSubtitle;
      ruleForm.action = "/api/notifications/update-rule";
      ruleIdInput.value = ruleId || "";
      ruleNameInput.value = ruleName || "";
      searchTermInput.value = ruleSearchTerm || "";
      isActiveInput.checked = ruleActive;

      // Set notification type based on frequency
      notificationTypeRadios.forEach((radio) => {
        if (radio.value === ruleFrequency) radio.checked = true;
      });

      // Trigger toggle to show correct sections
      toggleNotificationTypeSections();

      // Check the appropriate topic checkboxes in the VISIBLE section only
      const visibleSection = ruleFrequency === "weekly" ? weeklyOptionsSection : dailyOptionsSection;
      visibleSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]').forEach((checkbox) => {
        checkbox.checked = ruleTopics.includes(checkbox.value);
      });

      // For weekly rules, don't populate ward checkboxes (they're hidden)
      // For daily rules, populate ward checkboxes
      if (ruleFrequency === "daily") {
        const wardCheckboxes = ruleForm.querySelectorAll<HTMLInputElement>('input[name="wards"]');
        let hasSelectedWards = false;
        wardCheckboxes.forEach((checkbox) => {
          const isChecked = ruleWards.includes(checkbox.value);
          checkbox.checked = isChecked;
          if (isChecked) hasSelectedWards = true;
        });

        // Expand ward section if wards are selected
        if (hasSelectedWards) {
          wardSelectionContainer?.classList.remove("hidden");
          if (toggleWardsBtn) toggleWardsBtn.textContent = "Hide Wards";
        } else {
          wardSelectionContainer?.classList.add("hidden");
          if (toggleWardsBtn) toggleWardsBtn.textContent = "Show Wards";
        }
      }

      modal?.classList.remove("hidden");
    });
  });

  // Form validation before submission
  ruleForm?.addEventListener("submit", (e) => {
    const frequencyInput = document.getElementById("hidden_frequency") as HTMLInputElement | null;
    const errorMessage = findRuleFormError({
      frequency: frequencyInput?.value || "daily",
      searchTerm: searchTermInput.value.trim(),
      topicCount: ruleForm.querySelectorAll('input[name="topics"]:checked').length,
    });
    if (errorMessage) {
      e.preventDefault();
      alert(errorMessage);
    }
  });

  // Close modal
  cancelBtn?.addEventListener("click", () => {
    modal?.classList.add("hidden");
  });

  // Close on background click
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });
}
