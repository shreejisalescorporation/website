document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("inquiryForm");
  const dropdown = document.getElementById("dropdown");
  const dropdownLabel = document.getElementById("dropdownLabel");
  const responseMessage = document.getElementById("responseMessage");
  const captchaContainer = document.getElementById("recaptchaWidget");
  const captchaStatus = document.getElementById("captchaStatus");

  if (!form || !dropdown || !dropdownLabel || !responseMessage || !captchaContainer) {
    return;
  }

  const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
  const submitButton = form.querySelector('button[type="submit"]');
  const localHostPattern = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)$|^10\.|^192\.168\.|^172\.(1[6-9]|2\d|3[0-1])\./;
  const isLocalPreview = localHostPattern.test(window.location.hostname.toLowerCase());
  const captchaSiteKey = isLocalPreview
    ? captchaContainer.dataset.localSitekey
    : captchaContainer.dataset.sitekey;
  let captchaWidgetId = null;
  let captchaLoadAttempt = 0;
  let captchaLoadTimer = null;

  const getEndpoint = () => {
    if (!isLocalPreview) {
      return form.action;
    }

    if (window.location.port === "5000" || window.location.port === "5001") {
      return `${window.location.origin}/send_inquiry`;
    }

    return `${window.location.protocol}//${window.location.hostname}:5001/send_inquiry`;
  };

  const setResponse = (message, state) => {
    responseMessage.textContent = message;
    responseMessage.dataset.state = state;
  };

  const setCaptchaStatus = (message, state = "loading") => {
    if (!captchaStatus) {
      return;
    }

    captchaStatus.textContent = message;
    captchaStatus.dataset.state = state;
    captchaStatus.hidden = !message;
  };

  const renderCaptcha = () => {
    if (captchaWidgetId !== null) {
      return;
    }

    if (!captchaSiteKey) {
      setCaptchaStatus("Security check is not configured for this page.", "error");
      return;
    }

    if (!window.grecaptcha?.render) {
      setCaptchaStatus("Loading security check...", "loading");
      return;
    }

    try {
      captchaWidgetId = window.grecaptcha.render(captchaContainer, {
        sitekey: captchaSiteKey,
        callback: () => setResponse("", ""),
        "expired-callback": () => setResponse("The security check expired. Please complete it again.", "error"),
        "error-callback": () => setResponse("The security check could not load. Please refresh and try again.", "error"),
      });
      window.clearTimeout(captchaLoadTimer);
      setCaptchaStatus("");
    } catch (error) {
      console.error("reCAPTCHA render failed", error);
      setCaptchaStatus("Security check could not render here. Check the reCAPTCHA domain settings for this URL.", "error");
    }
  };

  const loadRecaptchaScript = (source, isFallback = false) => {
    const attempt = ++captchaLoadAttempt;
    const script = document.createElement("script");
    script.src = `${source}?onload=onRecaptchaLoad&render=explicit`;
    script.async = true;
    script.defer = true;

    window.onRecaptchaLoad = () => {
      if (attempt !== captchaLoadAttempt) {
        return;
      }

      renderCaptcha();
    };

    script.onerror = () => {
      if (attempt !== captchaLoadAttempt) {
        return;
      }

      window.clearTimeout(captchaLoadTimer);
      script.remove();

      if (!isFallback) {
        setCaptchaStatus("Loading security check from alternate host...", "loading");
        loadRecaptchaScript("https://www.recaptcha.net/recaptcha/api.js", true);
        return;
      }

      setCaptchaStatus("Security check could not load. Please refresh or disable browser blocking for reCAPTCHA.", "error");
    };

    document.head.appendChild(script);
    setCaptchaStatus("Loading security check...", "loading");
    captchaLoadTimer = window.setTimeout(() => {
      if (attempt !== captchaLoadAttempt || captchaWidgetId !== null) {
        return;
      }

      script.remove();

      if (!isFallback) {
        setCaptchaStatus("Loading security check from alternate host...", "loading");
        loadRecaptchaScript("https://www.recaptcha.net/recaptcha/api.js", true);
        return;
      }

      setCaptchaStatus("Security check is taking too long to load. Refresh the page and check that reCAPTCHA is allowed.", "error");
    }, 7000);
  };

  loadRecaptchaScript("https://www.google.com/recaptcha/api.js");

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
    delete responseMessage.dataset.state;

    const messageField = form.querySelector("#message");
    if (messageField) {
      messageField.setCustomValidity(
        messageField.value.trim().length < 5
          ? "Please enter a message with at least 5 non-whitespace characters."
          : "",
      );
    }

    if (!form.reportValidity()) {
      return;
    }

    const captchaToken = form.querySelector('[name="g-recaptcha-response"]')?.value;
    if (!captchaToken) {
      setResponse("Please complete the security check before sending your inquiry.", "error");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Sending...";
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);

    try {
      const response = await fetch(getEndpoint(), {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      const payload = await response.text();
      let data = {};

      try {
        data = payload ? JSON.parse(payload) : {};
      } catch {
        data = {};
      }

      if (!response.ok || data.status !== "success") {
        throw new Error(data.message || "The inquiry service is unavailable. Please call or email us instead.");
      }

      setResponse(data.message || "Thank you. Your inquiry has been sent.", "success");
      form.reset();
      if (captchaWidgetId !== null && window.grecaptcha) {
        window.grecaptcha.reset(captchaWidgetId);
      }
      updateDropdownLabel();
      setDropdownState(false);
    } catch (error) {
      const message = error.name === "AbortError"
        ? "The inquiry service took too long to respond. Please call or email us instead."
        : error.message || "Unable to send your inquiry. Please try again.";
      setResponse(message, "error");
    } finally {
      window.clearTimeout(timeout);
      submitButton.disabled = false;
      submitButton.textContent = "Submit Inquiry";
    }
  });
});
