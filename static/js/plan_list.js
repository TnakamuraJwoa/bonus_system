function redirectToPlanDetail(pk) {
    // ここでクリックされた要素を取得します
    var clickedElement = event.target;
    var this_tag_name = clickedElement.tagName.toLowerCase();
    // クリックされた要素がsvgタグかどうかを判定します
    if (!(this_tag_name === 'path' || this_tag_name === 'svg')) {
        // 遷移先のURLを生成します
        var url = '/plan-detail/' + pk + '/';

        // 遷移処理を実行します
        window.location.href = url;
    }
}

document.addEventListener("DOMContentLoaded", function() {
    const maxLength = 50; // 最大文字数を設定
    const descriptionElements = document.querySelectorAll('.plan-description');

    descriptionElements.forEach(element => {
        const description = element.textContent.trim();

        if (description.length > maxLength) {
            element.textContent = description.substring(0, maxLength - 3) + '...';
        }
    });
});
