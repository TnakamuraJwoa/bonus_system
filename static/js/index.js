// モーダルの定義
var myModal;
const calendar = document.querySelector('.calender-continer');

// モーダルを表示する関数
function openModal(modalId) {
    myModal = new bootstrap.Modal(document.getElementById(modalId));
    myModal.show();
}

// モーダルを閉じる関数
function closeModal() {
    if (myModal) {
        myModal.hide(); // myModalが定義されている場合にのみhide()を呼び出す
    }
}

// カレンダーを非表示にする関数
function closeCalendar() {
    calendar.style.display = 'none';
}

// チェックされた値とジャンル名を取得する関数
function getCheckedValuesAndGenres() {
    var checkedValues = [];  // 選択された値を格納する配列
    var genreNames = [];  // 選択されたジャンル名を格納する配列

    // チェックボックス要素の取得
    var checkboxes = document.querySelectorAll('.input-genre-checkbox-class:checked');

    // チェックされたチェックボックスの値とジャンル名を配列に追加
    checkboxes.forEach(function(checkbox) {
        checkedValues.push(checkbox.value);

        var genreNameElement = document.getElementById('id_genre_name_' + checkbox.value);
        if (genreNameElement) {
            var genreName = genreNameElement.textContent;
            genreNames.push(genreName);
        }
    });

    return { checkedValues: checkedValues, genreNames: genreNames };
}

// ジャンル名を設定する関数
function setGenreModel() {
    // チェックされた値とジャンル名を取得する関数
    var valuesAndGenres = getCheckedValuesAndGenres();

    // ジャンルのテキストを変更する
    var genreSpan = document.querySelector('.genre-name-text-class');

    if (valuesAndGenres.genreNames.length > 0) { // 空でなければ設定
        genreSpan.textContent = valuesAndGenres.genreNames.join(', ');
        document.getElementsByName('checkbox_value[]')[0].value = valuesAndGenres.checkedValues.join(', '); // checkbox_valueに選択された値を設定
    } else {
        genreSpan.textContent = "未設定";
        document.getElementsByName('checkbox_value[]')[0].value = ""; // checkbox_valueに選択された値を設定
    }
}

// 場所を設定する関数
function setPlaceModel() {
    // チェックされた値とジャンル名を取得する関数
    var plase_values = getPlaseVlues();
    // ジャンルのテキストを変更する
    var plaseSpan = document.querySelector('.place-name-text-class');

    if (plase_values.plaseNames.length > 0) { // 空でなければ設定
        plaseSpan.textContent = plase_values.plaseNames.join(', ');
        document.getElementsByName('place_checkbox_value[]')[0].value = plase_values.checkedValues.join(', '); // checkbox_valueに選択された値を設定
    } else {
        plaseSpan.textContent = "未設定";
        document.getElementsByName('place_checkbox_value[]')[0].value = ""; // checkbox_valueに選択された値を設定
    }
}

// チェックされた値と場所名を取得する関数
function getPlaseVlues() {
    var checkedValues = [];  // 選択された値を格納する配列
    var plaseNames = [];  // 選択されたジャンル名を格納する配列


    // チェックボックス要素の取得
    var checkboxes = document.querySelectorAll('.input-plase-checkbox-class:checked');

    // チェックされたチェックボックスの値とジャンル名を配列に追加
    checkboxes.forEach(function(checkbox) {
        checkedValues.push(checkbox.value);

        var plaseNameElement = document.getElementById('place_id-' + checkbox.value);
        if (plaseNameElement) {
            var plaseName = plaseNameElement.textContent;
            plaseNames.push(plaseName);
        }
    });

    return { checkedValues: checkedValues, plaseNames: plaseNames };
}

// 男性・女性の性別をクリックした時の処理
const manForm = document.querySelector('.manForm');
const womanForm = document.querySelector('.womanForm');

function updateGenderForm(genderValue) {
    if (genderValue=="1") {
        if (manForm.classList.contains('active')) {
            manForm.classList.remove('active'); // 'active' クラスを削除
            document.querySelector('input[name="gender_value[]"]').value = "";
        } else {
            manForm.classList.add('active'); // 'active' クラスを追加
            document.querySelector('input[name="gender_value[]"]').value = genderValue;
        }
        womanForm.classList.remove('active'); // 'active' クラスを削除
    }
    if (genderValue=="0") {
        if (womanForm.classList.contains('active')) {
            womanForm.classList.remove('active'); // 'active' クラスを削除
            document.querySelector('input[name="gender_value[]"]').value = "";
        } else {
            womanForm.classList.add('active'); // 'active' クラスを追加
            document.querySelector('input[name="gender_value[]"]').value = genderValue;
        }
        manForm.classList.remove('active'); // 'active' クラスを削除
    }
}

document.addEventListener("DOMContentLoaded", function() {
    const datePickerTrigger = document.getElementById("datepicker-trigger");
    const customDatePicker = document.getElementById("custom-datepicker");
    const datepickerContainers = document.getElementById('datepicker-container');


    // flatpickrでカレンダーを設定
    flatpickr(customDatePicker, {
        inline: true, // インラインモードでカレンダーを表示
        mode: "multiple", // 複数の日付を選択できるモード
        minDate: "today", // 今日以降の日付のみ選択可能
        onChange: function(selectedDates, dateStr, instance) {
            // カレンダーの値が変更されたときの処理
            const formattedDates = selectedDates.map(date => date.toLocaleDateString()).join(", ");
            datePickerTrigger.textContent = formattedDates || "未設定"; // 日付が空の場合は "未設定" を表示
            document.querySelector('input[name="event_date[]"]').value = formattedDates || ""; // 日付が空の場合は空文字を設定

            // 選択された日付の要素に背景色を設定（例：赤色）
            selectedDates.forEach(date => {
                const selectedDay = document.querySelector(`.flatpickr-day[data-date="${date.toISOString().split('T')[0]}"]`);
                if (selectedDay) {
                    selectedDay.style.backgroundColor = 'red';
                }
            });
        }
    });

//    // HTMLCollection の要素に対して個別にイベントリスナーを設定する
    datepickerContainers.addEventListener("click", function() {
        calendar.style.display = "block"; // カスタムカレンダーを表示
    });

    manForm.addEventListener('click', function() {
        updateGenderForm("1");
    });

    womanForm.addEventListener('click', function() {
        updateGenderForm("0");
    });

    // イベントジャンルと場所のモーダルを開く処理
    const modalMap = {
        'openGenreModal': 'genreModal',
        'openEventPlaceModal': 'placeModal'
    };

    Object.keys(modalMap).forEach(function(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.addEventListener('click', function() {
                openModal(modalMap[elementId]);
            });
        }
    });

    // イベントジャンルの確定ボタンクリック時に選択された値を取得して表示する例
    document.getElementById('id-genre-btn').addEventListener('click', function() {
        // チェックされた値とジャンル名を取得する関数
        setGenreModel();
        closeModal();
    });

    // イベントジャンルの確定ボタンクリック時に選択された値を取得して表示する例
    document.getElementById('id-genre-icon').addEventListener('click', function() {
        // チェックされた値とジャンル名を取得する関数
        setGenreModel();
        closeModal();
    });

    /*
    * - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - *
    */

    //場所を選択するmodelでの処理
    //spanタグをクリックしたら、checkboxをtrueまたは、falseにする
    const spans = document.querySelectorAll('.accordion-body span');

    spans.forEach(span => {
        span.addEventListener('click', function() {
            const checkbox = this.querySelector('.input-plase-checkbox-class'); // span内のチェックボックスを取得
            const checkboxClicked = event.target === checkbox; // クリックされた要素がチェックボックスかどうか判定

            // spanがクリックされた場合の処理
            if (!checkboxClicked) {
                checkbox.checked = !checkbox.checked;
            }
        });
    });

    // 場所modelのバツボタンをクリックした際の処理
    document.getElementById('id-place-icon').addEventListener('click', function() {
        setPlaceModel()
        closeModal();
    });

    // 場所modelの確定ボタンをクリックした際の処理
    document.getElementById('id-place-btn').addEventListener('click', function() {
        setPlaceModel()
        closeModal();
    });

    /*
    * - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - *
    */
});
