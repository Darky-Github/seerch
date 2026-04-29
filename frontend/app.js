async function search() {
  const q = document.getElementById("query").value;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const resultsBox = document.getElementById("results");

  resultsBox.innerHTML = "Searching...";

  const res = await fetch(`/search?q=${encodeURIComponent(q)}&mode=${mode}`);
  const data = await res.json();

  resultsBox.innerHTML = "";

  if (data.did_you_mean) {
    const hint = document.createElement("div");
    hint.innerHTML = `Did you mean: <b>${data.did_you_mean}</b>`;
    hint.onclick = () => {
      document.getElementById("query").value = data.did_you_mean;
      search();
    };
    resultsBox.appendChild(hint);
  }

  (data.results || []).forEach(item => {
    const div = document.createElement("div");

    div.innerHTML = `
      <a href="${item.url}" target="_blank">${item.title}</a>
      <div class="meta">
        ${item.url} | Score: ${item.score} | ${item.trust}
      </div>
      <div class="snippet">${item.snippet}</div>
    `;

    resultsBox.appendChild(div);
  });
}
