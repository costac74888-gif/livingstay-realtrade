(function (global) {
  "use strict";

  function svg(content, className) {
    return '<svg class="' + (className || "listing-icon") +
      '" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"' +
      ' stroke="currentColor" stroke-width="1.8" stroke-linecap="round"' +
      ' stroke-linejoin="round" aria-hidden="true">' + content + "</svg>";
  }

  global.LivingstayListingIcons = Object.freeze({
    heart: function (active) {
      return svg(
        '<path d="M12 21s-6.5-4.35-9.3-8.1C1 10.4 1.4 6.9 4.2 5.3' +
        ' 6.3 4.1 9 4.7 12 8c3-3.3 5.7-3.9 7.8-2.7' +
        ' 2.8 1.6 3.2 5.1 1.5 7.6C18.5 16.65 12 21 12 21z"/>' +
        (active ? '<path d="M12 18.8c-2.1-1.5-5.6-4.5-7.3-6.8-1-1.4-.7-3.5.8-4.4' +
          ' 1.5-.9 3.3-.2 4.5 1.2L12 10l2-1.2c1.2-1.4 3-2.1 4.5-1.2' +
          ' 1.5.9 1.8 3 .8 4.4-1.7 2.3-5.2 5.3-7.3 6.8z" fill="currentColor" stroke="none"/>' : "")
      );
    },
    chat: function () {
      return svg('<path d="M20 11.5a8 8 0 0 1-8 8 8.5 8.5 0 0 1-3.7-.85L4 20l1.35-3.7A8 8 0 1 1 20 11.5Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>');
    },
    share: function () {
      return svg('<circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><path d="m8.6 10.5 6.8-4"></path><path d="m8.6 13.5 6.8 4"></path>');
    },
    photoCount: function (count) {
      count = Number(count) || 0;
      if (count < 2) return "";
      return '<span class="ls-photo-count" aria-label="사진 ' + count + '장">' +
        '<svg class="ls-photo-count-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="3" y="5" width="18" height="14" rx="2"></rect><circle cx="8.5" cy="10" r="1.5"></circle><path d="m5 17 4.5-4 3 2.5 2-2 4.5 3.5"></path>' +
        '</svg><span>' + count + "</span></span>";
    },
  });
})(window);