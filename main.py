import sys
import cv2
import numpy as np
import tempfile
import traceback
import PyQt5.QtWidgets
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer
import os

class TextRecognitionDialog(PyQt5.QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文字识别结果")
        self.resize(800, 600)

        self.text_edit = PyQt5.QtWidgets.QTextEdit(self)
        self.text_edit.setPlaceholderText("这里显示识别文字")
        self.text_edit.setStyleSheet("background-color: #F0F0F0; padding: 5px;")

        self.word_count_label = PyQt5.QtWidgets.QLabel("字数：0", self)
        self.text_edit.textChanged.connect(self.update_word_count)

        self.copy_btn = PyQt5.QtWidgets.QPushButton("一键复制", self)
        self.copy_btn.setStyleSheet("background-color: #4A7ABD; color: white;")
        self.copy_btn.clicked.connect(self.copy_text)

        self.copy_tip_label = PyQt5.QtWidgets.QLabel("", self)
        self.copy_tip_label.setStyleSheet("color: green; font-size: 20px;")

        self.close_btn = PyQt5.QtWidgets.QPushButton("关闭", self)
        self.close_btn.setStyleSheet("background-color: #4A7ABD; color: white;")
        self.close_btn.clicked.connect(self.close)

        outer_layout = PyQt5.QtWidgets.QHBoxLayout()
        outer_layout.addWidget(self.text_edit, stretch=3)

        right_layout = PyQt5.QtWidgets.QVBoxLayout()
        right_layout.setSpacing(20)

        right_layout.addWidget(self.word_count_label, alignment=Qt.AlignCenter)
        right_layout.addStretch()

        buttons_container = PyQt5.QtWidgets.QWidget()
        buttons_layout = PyQt5.QtWidgets.QVBoxLayout(buttons_container)
        buttons_layout.setSpacing(30)
        buttons_layout.setAlignment(Qt.AlignCenter)

        buttons_layout.addWidget(self.copy_tip_label, alignment=Qt.AlignCenter)
        buttons_layout.addWidget(self.copy_btn)
        buttons_layout.addWidget(self.close_btn)

        right_layout.addWidget(buttons_container, alignment=Qt.AlignCenter)
        right_layout.addStretch()

        outer_layout.addLayout(right_layout, stretch=1)
        self.setLayout(outer_layout)

    def set_recognized_text(self, text):
        self.text_edit.setText(text)
        self.update_word_count()

    def update_word_count(self):
        text = self.text_edit.toPlainText()
        self.word_count_label.setText(f"字数：{len(text)}")

    def copy_text(self):
        text = self.text_edit.toPlainText()
        clipboard = PyQt5.QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        self.copy_tip_label.setText("已复制到剪贴板")
        self.copy_tip_label.show()
        QTimer.singleShot(2000, self.copy_tip_label.hide)


class MainWindow(PyQt5.QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片型文档编辑处理软件")
        self.resize(800, 600)
        self.current_pixmap = None  # 保存当前显示的图片
        self.original_pixmap = None  # 保存原始图片，用于处理后恢复
        self.current_image_path = None  # 当前图片的文件路径（如果有）

        # PaddleOCR 实例（懒加载）
        self.ocr = None

        # 添加导出PDF的动作到导出菜单
        self.init_ui()

    def init_ui(self):
        # 中心控件与主布局
        central_widget = PyQt5.QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = PyQt5.QtWidgets.QHBoxLayout(central_widget)

        # 左侧：图片拖放区域
        self.left_label = PyQt5.QtWidgets.QLabel(central_widget)
        self.left_label.setAlignment(Qt.AlignCenter)
        self.left_label.setAcceptDrops(True)  # 允许拖放
        self.init_drag_area()

        # 绑定拖放事件到标签
        self.left_label.dragEnterEvent = self.drag_enter_event
        self.left_label.dragMoveEvent = self.drag_move_event
        self.left_label.dropEvent = self.drop_event

        main_layout.addWidget(self.left_label, stretch=3)

        # 右侧：功能按钮区域
        right_widget = PyQt5.QtWidgets.QWidget(central_widget)
        right_layout = PyQt5.QtWidgets.QVBoxLayout(right_widget)
        right_layout.setSpacing(15)
        main_layout.addWidget(right_widget, stretch=2)

        # 图片处理按钮
        self.process_btn = PyQt5.QtWidgets.QPushButton("图片处理", right_widget)
        self.process_btn.setStyleSheet("background-color: #4A7ABD; color: white; padding: 8px;")
        self.process_menu = PyQt5.QtWidgets.QMenu(self)
        self.process_menu.addAction("灰度图片", self.process_grayscale)
        self.process_menu.addAction("黑白图片", self.process_bw)
        self.process_btn.setMenu(self.process_menu)
        right_layout.addWidget(self.process_btn)

        # 图片导出按钮
        self.export_btn = PyQt5.QtWidgets.QPushButton("图片导出", right_widget)
        self.export_btn.setStyleSheet("background-color: #4A7ABD; color: white; padding: 8px;")
        self.export_menu = PyQt5.QtWidgets.QMenu(self)
        self.export_menu.addAction("导出当前图片为.jpg格式", self.export_jpg)
        self.export_menu.addAction("导出当前图片为.png格式", self.export_png)
        self.export_btn.setMenu(self.export_menu)
        right_layout.addWidget(self.export_btn)

        # 文字识别按钮
        self.ocr_btn = PyQt5.QtWidgets.QPushButton("文字识别", right_widget)
        self.ocr_btn.setStyleSheet("background-color: #4A7ABD; color: white; padding: 8px;")
        self.ocr_btn.clicked.connect(self.open_ocr_dialog)
        right_layout.addWidget(self.ocr_btn)

        # 退出按钮
        self.exit_btn = PyQt5.QtWidgets.QPushButton("退出", right_widget)
        self.exit_btn.setStyleSheet("background-color: #4A7ABD; color: white; padding: 8px;")
        self.exit_btn.clicked.connect(self.close)
        right_layout.addWidget(self.exit_btn)

        # 添加点击事件
        self.left_label.mousePressEvent = self.on_label_clicked

    def init_drag_area(self):
        self.left_label.setText("📷\n\n单击或拖拽待处理图片至此处")
        self.left_label.setStyleSheet("""
            background-color: #D0D0D0; 
            color: #888888; 
            font-size: 20px;
            border: 2px dashed #AAAAAA;
        """)

    def on_label_clicked(self, event):
        if event.button() == Qt.LeftButton:  # 只响应左键点击
            file_path, _ = PyQt5.QtWidgets.QFileDialog.getOpenFileName(
                self, "选择图片", "",
                "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
            )
            if file_path:
                self.display_image(file_path)

    # 拖拽进入事件
    def drag_enter_event(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile().lower()
                if file_path.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    # 拖拽移动事件
    def drag_move_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    # 拖拽释放事件
    def drop_event(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if os.path.isfile(file_path) and file_path.lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')):
                self.display_image(file_path)
                event.acceptProposedAction()
            else:
                PyQt5.QtWidgets.QMessageBox.warning(self, "错误", "请拖放有效的图片文件")
                event.ignore()
        else:
            event.ignore()

    def display_image(self, file_path):
        try:
            # 使用OpenCV读取（支持中文路径）
            img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)

            if img is not None:
                # 转换颜色空间从BGR到RGB
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = img.shape
                bytes_per_line = ch * w
                q_img = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            else:
                # 备用方案：使用Qt加载
                q_img = QImage(file_path)
                if q_img.isNull():
                    raise ValueError("无法读取图片文件")

            # 转换为QPixmap并显示（自动适应标签大小）
            self.current_pixmap = QPixmap.fromImage(q_img)
            self.original_pixmap = self.current_pixmap.copy()  # 保存原始图片
            self.current_image_path = file_path
            self.update_image_display()

            # 重置标签样式
            self.left_label.setText("")
            self.left_label.setStyleSheet("background-color: #D0D0D0; border: none;")

        except Exception as e:
            print(f"加载图片错误: {str(e)}")
            PyQt5.QtWidgets.QMessageBox.warning(self, "图片加载错误",
                                f"无法加载图片:\n{file_path}\n错误: {str(e)}")
            self.left_label.setText("图片加载失败\n请尝试其他图片")
            self.left_label.setStyleSheet("""
                background-color: #D0D0D0; 
                color: #FF0000; 
                font-size: 20px;
                border: 2px dashed #FF0000;
            """)

    def update_image_display(self):
        """更新图片显示，保持比例适应标签"""
        if self.current_pixmap:
            scaled_pixmap = self.current_pixmap.scaled(
                self.left_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.left_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        """窗口大小改变时重新调整图片"""
        if self.current_pixmap:
            self.update_image_display()
        super().resizeEvent(event)

    def open_ocr_dialog(self):
        if not self.current_pixmap:
            PyQt5.QtWidgets.QMessageBox.information(self, "提示", "请先加载图片")
            return

        # 准备界面提示（防止界面卡住）
        self.ocr_btn.setEnabled(False)
        old_text = self.ocr_btn.text()
        self.ocr_btn.setText("识别中...")
        PyQt5.QtWidgets.QApplication.processEvents()

        # 获取需要识别的图片路径；如果没有原始路径则把当前pixmap保存到临时文件
        image_path = self.current_image_path
        temp_file = None
        try:
            if image_path is None:
                # 保存到临时文件
                temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
                os.close(temp_fd)
                self.current_pixmap.save(temp_path)
                image_path = temp_path
                temp_file = temp_path

            # 执行识别（可能耗时）
            recognized_text = self.perform_ocr(image_path)

            dialog = TextRecognitionDialog(self)
            dialog.set_recognized_text(recognized_text)
            dialog.exec_()

        except Exception as e:
            traceback.print_exc()
            PyQt5.QtWidgets.QMessageBox.warning(self, "识别错误", f"OCR 识别出错:\n{str(e)}")

        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            # 恢复按钮状态
            self.ocr_btn.setEnabled(True)
            self.ocr_btn.setText(old_text)

    def perform_ocr(self, image_path: str) -> str:
        """PaddleOCR Pipeline 版本识别（predict 输出解析）"""
        try:
            from paddleocr import PaddleOCR
        except Exception:
            raise RuntimeError(
                "未检测到 paddleocr，请先安装：\n"
                "pip install paddleocr\n"
                "若报错请先安装 paddlepaddle。"
            )
        # 创建模型（只创建一次） ， 目前还没有实现使用本地模型
        if self.ocr is None:
            self.ocr = PaddleOCR(
                use_textline_orientation=True,
                lang='ch'
            )

        results = self.ocr.predict(image_path)
        lines = []
        if results and isinstance(results, list):
            res = results[0]
            rec_texts = res.get("rec_texts", [])
            for text in rec_texts:
                lines.append(text)

        if not lines:
            return "未识别到文字"
        return "\n".join(lines)

    def process_grayscale(self):
        """灰度处理功能实现"""
        if not self.current_pixmap:
            PyQt5.QtWidgets.QMessageBox.information(self, "提示", "请先加载图片")
            return

        # 将QPixmap转换为QImage
        q_image = self.current_pixmap.toImage()

        # 转换为OpenCV格式
        width = q_image.width()
        height = q_image.height()
        ptr = q_image.bits()
        ptr.setsize(height * width * 4)
        arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))

        # 转换为灰度图
        gray = cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
        gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

        # 转换回QPixmap并显示
        h, w, ch = gray_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(gray_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.current_pixmap = QPixmap.fromImage(q_img)
        self.update_image_display()

    def process_bw(self):
        """黑白处理功能实现"""
        if not self.current_pixmap:
            PyQt5.QtWidgets.QMessageBox.information(self, "提示", "请先加载图片")
            return

        # 将QPixmap转换为QImage
        q_image = self.current_pixmap.toImage()

        # 转换为OpenCV格式
        width = q_image.width()
        height = q_image.height()
        ptr = q_image.bits()
        ptr.setsize(height * width * 4)
        arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))

        # 先转换为灰度图，再进行二值化处理
        gray = cv2.cvtColor(arr, cv2.COLOR_RGBA2GRAY)
        bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY,7,10)
        bw_rgb = cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)

        # 转换回QPixmap并显示
        h, w, ch = bw_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(bw_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.current_pixmap = QPixmap.fromImage(q_img)
        self.update_image_display()

    def export_jpg(self):
        """导出为JPG格式功能实现"""
        if not self.current_pixmap:
            PyQt5.QtWidgets.QMessageBox.information(self, "提示", "请先加载图片")
            return

        file_path, _ = PyQt5.QtWidgets.QFileDialog.getSaveFileName(
            self, "导出为JPG", "", "JPG图片 (*.jpg)"
        )

        if file_path:
            # 确保文件扩展名正确
            if not file_path.lower().endswith('.jpg'):
                file_path += '.jpg'

            # 保存图片
            if self.current_pixmap.save(file_path, "JPG"):
                PyQt5.QtWidgets.QMessageBox.information(self, "成功", f"图片已导出至:\n{file_path}")
            else:
                PyQt5.QtWidgets.QMessageBox.warning(self, "失败", "无法保存图片，请重试")

    def export_png(self):
        """导出为PNG格式功能实现"""
        if not self.current_pixmap:
            PyQt5.QtWidgets.QMessageBox.information(self, "提示", "请先加载图片")
            return

        file_path, _ = PyQt5.QtWidgets.QFileDialog.getSaveFileName(
            self, "导出为PNG", "", "PNG图片 (*.png)"
        )

        if file_path:
            # 确保文件扩展名正确
            if not file_path.lower().endswith('.png'):
                file_path += '.png'

            # 保存图片
            if self.current_pixmap.save(file_path, "PNG"):
                PyQt5.QtWidgets.QMessageBox.information(self, "成功", f"图片已导出至:\n{file_path}")
            else:
                PyQt5.QtWidgets.QMessageBox.warning(self, "失败", "无法保存图片，请重试")



if __name__ == "__main__":
    app = PyQt5.QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
