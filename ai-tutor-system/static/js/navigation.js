/**
 * 工作台页面导航
 * 控制侧边栏点击和页面切换
 */

/**
 * 切换到指定工作台页面
 * @param {string} pageId - 页面标识，对应 data-page 属性
 */
function showWorkbenchPage(pageId) {
    // 隐藏所有页面区块
    document.querySelectorAll('.page-section').forEach(function (section) {
        section.classList.remove('active');
    });

    // 显示目标页面
    var target = document.querySelector('.page-section[data-page="' + pageId + '"]');
    if (target) {
        target.classList.add('active');
    }

    // 更新侧边栏激活状态
    document.querySelectorAll('[data-nav]').forEach(function (item) {
        item.classList.remove('active');
    });
    var activeNav = document.querySelector('[data-nav="' + pageId + '"]');
    if (activeNav) {
        activeNav.classList.add('active');
    }
}

/**
 * 初始化导航事件
 */
function initNavigation() {
    document.querySelectorAll('[data-nav]').forEach(function (navItem) {
        navItem.addEventListener('click', function (e) {
            e.preventDefault();
            var pageId = navItem.getAttribute('data-nav');
            showWorkbenchPage(pageId);
        });
    });
}

// DOM 就绪后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavigation);
} else {
    initNavigation();
}
