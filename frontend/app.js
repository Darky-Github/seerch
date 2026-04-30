let currentPage = 0;
const LIMIT = 10;

function highlight(text, words) {
  words.forEach(w => {
    const regex = new RegExp(`(${w})`, "gi");
    text = text.replace(regex, "<mark>$1</mark>");
  });
  return text;
}

async function search(page = 0) {
  const startTime = performance.now();

  const q = document.getElementById("query").value;
  const mode = document.querySelector('input[name="mode"]:checked').value;

  currentPage = page;

  const offset = page * LIMIT;

  const resultsBox = document.getElementById("results");
  const infoBox = document.getElementById("info");

  resultsBox.innerHTML = "Searching...";

  const res = await fetch(`/search?q=${encodeURIComponent(q)}&mode=${mode}&limit=${LIMIT}&offset=${offset}`);
  const data = await res.json();

  const timeTaken = ((performance.now() - startTime) / 1000).toFixed(2);

  resultsBox.innerHTML = "";
  infoBox.innerHTML = `About ${data.results.length} results (${timeTaken}s)`;

  const words = q.toLowerCase().split(" ");

  data.results.forEach(item => {
    const div = document.createElement("div");
    div.className = "result";

    const snippet = highlight(item.snippet, words);

    div.innerHTML = `
      <a href="${item.url}" target="_blank">${item.title || item.url}</a>
      <div class="meta">${item.url} • Score: ${item.score}</div>
      <div class="snippet">${snippet}</div>
    `;

    resultsBox.appendChild(div);
  });

  renderPagination();
}

function renderPagination() {
  const pagination = document.getElementById("pagination");
  pagination.innerHTML = "";

  for (let i = 0; i < 5; i++) {
    const btn = document.createElement("span");
    btn.className = "page-btn" + (i === currentPage ? " active" : "");
    btn.innerText = i + 1;

    btn.onclick = () => search(i);
    pagination.appendChild(btn);
  }
}

/* THEME */

function toggleTheme() {
  document.body.classList.toggle("light");
}

/* ENTER KEY */

document.getElementById("query").addEventListener("keypress", function (e) {
  if (e.key === "Enter") search();
});
