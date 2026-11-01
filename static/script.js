// Live search for the item cards already rendered by Flask.
document.addEventListener("DOMContentLoaded", () => {
  const photoInput = document.querySelector("#photo-input");
  const photoPreview = document.querySelector("#photo-preview");

  if (photoInput && photoPreview) {
    photoInput.addEventListener("change", () => {
      const photo = photoInput.files[0];
      if (!photo) {
        photoPreview.hidden = true;
        photoPreview.removeAttribute("src");
        return;
      }
      photoPreview.src = URL.createObjectURL(photo);
      photoPreview.hidden = false;
    });
  }

  const searchInput = document.querySelector('.filters input[name="q"]');
  const grid = document.querySelector(".card-grid");

  if (!searchInput || !grid) return;

  const cards = Array.from(grid.querySelectorAll(".item-card"));
  const resultLabel = document.querySelector(".results-line span");
  const noMatch = document.createElement("p");

  noMatch.className = "empty-search";
  noMatch.textContent = "No matching items found.";
  noMatch.setAttribute("role", "status");
  noMatch.hidden = true;
  grid.insertAdjacentElement("afterend", noMatch);

  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    cards.forEach((card) => {
      const matches = card.textContent.toLowerCase().includes(query);
      card.hidden = !matches;
      if (matches) visibleCount += 1;
    });

    noMatch.hidden = visibleCount !== 0;
    if (resultLabel) {
      resultLabel.textContent = `${visibleCount} listing${visibleCount === 1 ? "" : "s"}`;
    }
  });
});
