document.addEventListener("DOMContentLoaded", () => {
  const hamburger = document.querySelector(".hamburger");
  const navLinks = document.querySelector(".nav-links");

  if (hamburger && navLinks) {
    hamburger.setAttribute("role", "button");
    hamburger.setAttribute("tabindex", "0");
    hamburger.setAttribute("aria-expanded", "false");

    const toggleMenu = () => {
      const isOpen = navLinks.classList.toggle("active");
      hamburger.setAttribute("aria-expanded", String(isOpen));
    };

    hamburger.addEventListener("click", toggleMenu);
    hamburger.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleMenu();
      }
    });

    document.addEventListener("click", (event) => {
      if (!navLinks.contains(event.target) && !hamburger.contains(event.target)) {
        navLinks.classList.remove("active");
        hamburger.setAttribute("aria-expanded", "false");
      }
    });
  }

  const currentPath = window.location.pathname.replace(/\/$/, "") || "/";

  if (!document.querySelector(".floating-contact")) {
    const floatingContact = document.createElement("div");
    floatingContact.classList.add("footer-socials", "floating-contact");
    floatingContact.setAttribute("role", "group");
    floatingContact.setAttribute("aria-label", "Quick contact");

    const contactLinks = [
      ["mailto:shreejisalescorp.in@gmail.com", "Email shreejisalescorp.in@gmail.com", "fas fa-envelope"],
      ["tel:+919427020838", "Call +91 94270 20838", "fas fa-phone"],
      ["https://wa.me/919427020838", "WhatsApp +91 94270 20838", "fab fa-whatsapp"]
    ];

    contactLinks.forEach(([href, label, iconClass]) => {
      const link = document.createElement("a");
      const icon = document.createElement("i");
      link.href = href;
      link.setAttribute("aria-label", label);
      link.title = label;
      icon.className = iconClass;
      icon.setAttribute("aria-hidden", "true");
      link.appendChild(icon);
      floatingContact.appendChild(link);
    });

    document.body.appendChild(floatingContact);
  }

  if (navLinks) {
    const navigationItems = [
      ["/faq/", "FAQs"],
      ["/contact/", "Contact"]
    ];

    navigationItems.forEach(([href, label]) => {
      if (navLinks.querySelector(`a[href="${href}"]`)) {
        return;
      }

      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = href;
      link.textContent = label;
      item.appendChild(link);

      const aboutLink = navLinks.querySelector('a[href="/about/"]');
      if (aboutLink && href === "/faq/") {
        aboutLink.parentElement.before(item);
      } else {
        navLinks.querySelector("ul")?.appendChild(item);
      }
    });
  }

  document.querySelectorAll(".nav-links a").forEach((link) => {
    const href = link.getAttribute("href");
    if (!href) {
      return;
    }

    const normalizedHref = href.replace(/\/$/, "") || "/";
    if (normalizedHref === currentPath) {
      link.classList.add("is-active");
    }
  });

  const carousel = document.querySelector("[data-carousel]");
  if (carousel) {
    const slides = Array.from(carousel.querySelectorAll(".carousel-slide"));
    const dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    const previousButton = carousel.querySelector("[data-carousel-prev]");
    const nextButton = carousel.querySelector("[data-carousel-next]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let activeIndex = 0;
    let rotationTimer;

    const showSlide = (nextIndex) => {
      activeIndex = (nextIndex + slides.length) % slides.length;

      slides.forEach((slide, index) => {
        const isActive = index === activeIndex;
        slide.classList.toggle("is-active", isActive);
        slide.setAttribute("aria-hidden", String(!isActive));
      });

      dots.forEach((dot, index) => {
        const isActive = index === activeIndex;
        dot.classList.toggle("is-active", isActive);
        dot.setAttribute("aria-selected", String(isActive));
      });
    };

    const stopRotation = () => {
      window.clearInterval(rotationTimer);
    };

    const startRotation = () => {
      if (reducedMotion || slides.length < 2) {
        return;
      }

      stopRotation();
      rotationTimer = window.setInterval(() => showSlide(activeIndex + 1), 6500);
    };

    previousButton?.addEventListener("click", () => {
      showSlide(activeIndex - 1);
      startRotation();
    });

    nextButton?.addEventListener("click", () => {
      showSlide(activeIndex + 1);
      startRotation();
    });

    dots.forEach((dot, index) => {
      dot.addEventListener("click", () => {
        showSlide(index);
        startRotation();
      });
    });

    carousel.addEventListener("mouseenter", stopRotation);
    carousel.addEventListener("mouseleave", startRotation);
    carousel.addEventListener("focusin", stopRotation);
    carousel.addEventListener("focusout", (event) => {
      if (!carousel.contains(event.relatedTarget)) {
        startRotation();
      }
    });

    carousel.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        showSlide(activeIndex - 1);
        startRotation();
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        showSlide(activeIndex + 1);
        startRotation();
      }
    });

    showSlide(0);
    startRotation();
  }
});
