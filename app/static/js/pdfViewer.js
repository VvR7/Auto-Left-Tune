// PDF查看器模块
class PdfViewer {
    constructor() {
        // 初始化PDF.js
        pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/js/pdfjs/build/pdf.worker.mjs';

        // DOM元素
        this.pdfViewer = document.getElementById('pdf-viewer');
        this.pdfContainer = document.getElementById('pdf-container');

        // 当前加载的PDF文档
        this.currentPdfDoc = null;
    }

    // 从URL加载PDF
    async loadPdfFromUrl(url) {
        try {
            // 清空之前的PDF内容
            this.pdfViewer.innerHTML = '';

            // 加载新PDF文档
            const loadingTask = pdfjsLib.getDocument({ url });
            this.currentPdfDoc = await loadingTask.promise;

            // 显示加载的页面数量
            console.log(`PDF加载成功，共 ${this.currentPdfDoc.numPages} 页`);

            // 渲染所有页面
            for (let pageNum = 1; pageNum <= this.currentPdfDoc.numPages; pageNum++) {
                await this.renderPage(pageNum);
            }

            return true;
        } catch (error) {
            console.error('加载PDF时出错:', error);
            this.pdfViewer.innerHTML = `<p class="error">PDF加载失败: ${error.message}</p>`;
            return false;
        }
    }

    // 渲染单个PDF页面
    async renderPage(pageNumber) {
        try {
            // 获取页面
            const page = await this.currentPdfDoc.getPage(pageNumber);

            // 计算缩放比例，使页面适合容器宽度
            const containerWidth = this.pdfContainer.clientWidth - 40; // 减去padding
            const originalViewport = page.getViewport({ scale: 1 });
            const scale = containerWidth / originalViewport.width;
            const viewport = page.getViewport({ scale });

            // 创建页面的canvas元素
            const canvas = document.createElement('canvas');
            canvas.className = 'pdf-page';
            canvas.width = viewport.width;
            canvas.height = viewport.height;

            // 添加到查看器
            this.pdfViewer.appendChild(canvas);

            // 渲染页面到canvas
            const renderContext = {
                canvasContext: canvas.getContext('2d'),
                viewport: viewport
            };

            await page.render(renderContext).promise;
        } catch (error) {
            console.error(`渲染页面 ${pageNumber} 时出错:`, error);
        }
    }
}

// 创建PDF查看器实例
const pdfViewer = new PdfViewer();

// 导出PDF查看器
export default pdfViewer; 