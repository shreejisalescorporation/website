document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("inquiryForm");
  const dropdown = document.getElementById("dropdown");
  const dropdownLabel = document.getElementById("dropdownLabel");
  const responseMessage = document.getElementById("responseMessage");

  if (!form || !dropdown || !dropdownLabel || !responseMessage) {
    return;
  }

  const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
  const submitButton = form.querySelector('button[type="submit"]');

  const setDropdownState = (isOpen) => {
    dropdown.classList.toggle("open", isOpen);
    dropdownLabel.setAttribute("aria-expanded", String(isOpen));
  };

  const updateDropdownLabel = () => {
    const selected = Array.from(checkboxes)
      .filter((item) => item.checked)
      .map((item) => item.parentElement.textContent.trim());

    dropdownLabel.textContent = selected.length ? selected.join(", ") : "Select Products";
  };

  dropdownLabel.addEventListener("click", () => {
    setDropdownState(!dropdown.classList.contains("open"));
  });

  dropdownLabel.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setDropdownState(!dropdown.classList.contains("open"));
    }

    if (event.key === "Escape") {
      setDropdownState(false);
    }
  });

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", updateDropdownLabel);
  });

  document.addEventListener("click", (event) => {
    if (!dropdown.contains(event.target)) {
      setDropdownState(false);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    responseMessage.textContent = "";

    if (!form.reportValidity()) {
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Sending...";

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
      });
      const data = await response.json();

      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "Unable to send your inquiry. Please try again.");
      }

      responseMessage.textContent = data.message;
      responseMessage.style.color = "#6e1704";
      form.reset();
      updateDropdownLabel();
      setDropdownState(false);
    } catch (error) {
      responseMessage.textContent = error.message || "Unable to send your inquiry. Please try again.";
      responseMessage.style.color = "#9b1d0d";
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Submit Inquiry";
    }
  });
});
