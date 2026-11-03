'use strict';
/** playwright 统一入口（本地优先，回退全局安装） */
module.exports = require('./config').loadPlaywright();
