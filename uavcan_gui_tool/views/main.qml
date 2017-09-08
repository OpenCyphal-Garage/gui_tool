import QtQuick 2.3
import QtQuick.Window 2.2
import QtQuick.Controls 1.3

Window {
    visible: true

    MouseArea {
        anchors.fill: parent
        onClicked: {
            Qt.quit();
        }
    }

    Text {
        text: qsTr("Hello World")
        anchors.centerIn: parent
    }

    Text {
        id: text1
        x: -211
        y: -66
        width: 284
        height: 33
        text: qsTr("heaheheheh ")
        font.pixelSize: 12
    }

    Button {
        id: button1
        x: -152
        y: -15
        text: qsTr("hehe")
    }

    Image {
        id: image1
        x: -211
        y: -185
        width: 100
        height: 100
        source: "qrc:/qtquickplugin/images/template_image.png"
    }
}

