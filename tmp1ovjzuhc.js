
(function(){
  const badge = document.getElementById("envBadge");
  if (!badge) return;
  const isProd = /homenstay\.com$|livingstay-realtrade\.replit\.app$/.test(location.hostname);
  badge.textContent = isProd ? "🔴 운영" : "⚪ 개발";
  badge.style.background = isProd ? "#FDE8E8" : "#EEE";
  badge.style.color = isProd ? "#C0392B" : "#666";
})();
