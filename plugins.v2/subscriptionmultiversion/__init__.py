"""
订阅多资源版本订阅插件
提供基于订阅的多资源版本管理和过滤功能
"""

import json
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

from app.core.config import settings
from app.core.context import Context, MediaInfo, MetaInfo, TorrentInfo
from app.plugins import _PluginBase
from app.schemas.workflow import ActionContext
from app.helper.torrent import TorrentHelper
from app.helper.subscribe import SubscribeHelper
from app.helper.sites import SitesHelper
from app.modules.filter import FilterModule
from app.chain.search import SearchChain
from app.chain.download import DownloadChain
from app.chain.media import MediaChain
from app.helper.downloader import DownloaderHelper
from app.db.subscribe_oper import SubscribeOper
from app.db.models.subscribe import Subscribe
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.models.downloadhistory import DownloadHistory
from app.schemas.types import MediaType
from app.log import logger


class SubscriptionMultiVersion(_PluginBase):
    """
    订阅多资源版本订阅插件
    """

    # 插件名称
    plugin_name = "订阅多资源版本订阅"
    # 插件描述
    plugin_desc = "提供基于订阅的多资源版本管理和过滤功能"
    # 插件图标
    plugin_icon = "subscribemultiversion.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "Claude"
    # 作者主页
    author_url = "https://github.com/claude"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscriptionmultiversion_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _sites_helper: SitesHelper = None
    _torrent_helper: TorrentHelper = None
    _subscribe_helper: SubscribeHelper = None
    _filter_module: FilterModule = None
    _search_chain: SearchChain = None
    _download_chain: DownloadChain = None
    _downloader_helper: DownloaderHelper = None
    _subscribe_oper: SubscribeOper = None
    _download_history_oper: DownloadHistoryOper = None
    _enabled: bool = False
    _enable_search: bool = True
    _enable_filter: bool = True
    _default_filter_rules: str = ""

    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._enabled = config.get("enabled")
            self._enable_search = config.get("enable_search", True)
            self._enable_filter = config.get("enable_filter", True)
            self._default_filter_rules = config.get("default_filter_rules", "")

        # 初始化助手
        self._sites_helper = SitesHelper()
        self._torrent_helper = TorrentHelper()
        self._subscribe_helper = SubscribeHelper()
        self._filter_module = FilterModule()
        self._search_chain = SearchChain()
        self._download_chain = DownloadChain()
        self._downloader_helper = DownloaderHelper()
        self._subscribe_oper = SubscribeOper()
        self._download_history_oper = DownloadHistoryOper()
        self._media_chain = MediaChain()

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        """
        return [
            {
                "path": "/query",
                "endpoint": self.query_subscribe_torrents_api,
                "methods": ["POST"],
                "summary": "查询订阅种子",
                "description": "根据订阅查询种子资源",
                "auth": "apikey"
            },
            {
                "path": "/filter",
                "endpoint": self.filter_torrents_api,
                "methods": ["POST"],
                "summary": "过滤种子",
                "description": "根据规则过滤种子资源",
                "auth": "apikey"
            },
            {
                "path": "/config",
                "endpoint": self.get_config_api,
                "methods": ["GET"],
                "summary": "获取插件配置",
                "description": "获取插件当前配置信息",
                "auth": "apikey"
            },
            {
                "path": "/status",
                "endpoint": self.get_status_api,
                "methods": ["GET"],
                "summary": "获取插件状态",
                "description": "获取插件运行状态信息",
                "auth": "apikey"
            }
        ]

    def query_subscribe_torrents_api(self):
        """
        查询订阅种子API端点
        """
        from fastapi import HTTPException
        try:
            if not self._enabled:
                raise HTTPException(status_code=400, detail="插件未启用")

            if not self._enable_search:
                raise HTTPException(status_code=400, detail="查询功能未启用")

            # 这里可以添加查询逻辑，返回查询结果
            return {
                "success": True,
                "message": "查询功能可用",
                "data": {
                    "enabled": self._enabled,
                    "search_enabled": self._enable_search,
                    "filter_enabled": self._enable_filter
                }
            }
        except Exception as e:
            logger.error(f"查询订阅种子API调用失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def filter_torrents_api(self):
        """
        过滤种子API端点
        """
        from fastapi import HTTPException
        try:
            if not self._enabled:
                raise HTTPException(status_code=400, detail="插件未启用")

            if not self._enable_filter:
                raise HTTPException(status_code=400, detail="过滤功能未启用")

            # 这里可以添加过滤逻辑，返回过滤结果
            return {
                "success": True,
                "message": "过滤功能可用",
                "data": {
                    "enabled": self._enabled,
                    "filter_enabled": self._enable_filter,
                    "default_filter_rules": self._default_filter_rules
                }
            }
        except Exception as e:
            logger.error(f"过滤种子API调用失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_config_api(self):
        """
        获取插件配置API端点
        """
        from fastapi import HTTPException
        try:
            config = self.get_config()
            if not config:
                config = {
                    "enabled": False,
                    "enable_search": True,
                    "enable_filter": True,
                    "default_filter_rules": ""
                }

            return {
                "success": True,
                "message": "获取配置成功",
                "data": config
            }
        except Exception as e:
            logger.error(f"获取配置API调用失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_status_api(self):
        """
        获取插件状态API端点
        """
        try:
            return {
                "success": True,
                "message": "获取状态成功",
                "data": {
                    "enabled": self._enabled,
                    "search_enabled": self._enable_search,
                    "filter_enabled": self._enable_filter,
                    "plugin_version": self.plugin_version,
                    "plugin_author": self.plugin_author
                }
            }
        except Exception as e:
            logger.error(f"获取状态API调用失败: {str(e)}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(e))

    def get_actions(self) -> List[Dict[str, Any]]:
        """
        获取插件工作流动作
        """
        if not self._enabled:
            return []

        actions = []

        # 订阅多版本过滤动作（合并查询和过滤）
        actions.append({
            "action_id": "subscribe_multiversion_filter",
            "name": "subscribe_multiversion_filter",
            "func": self.subscribe_multiversion_filter,
            "description": "查询订阅种子并进行多版本过滤",
            "kwargs": {
                "subscribe_ids": [],
                "search_sites": [],
                "rule_groups": [],
                "quality": None,
                "resolution": None,
                "effect": None,
                "include": None,
                "exclude": None,
                "size": None,
                "prioritize_downloaded": True
            }
        })

        return actions

    def subscribe_multiversion_filter(self, context: ActionContext, **kwargs) -> Tuple[bool, ActionContext]:
        """
        订阅多版本过滤动作（合并查询和过滤）
        :param context: 工作流上下文
        :param kwargs: 动作参数
        :return: (执行状态, 更新后的上下文)
        """
        try:
            # 获取查询参数
            subscribe_ids = kwargs.get("subscribe_ids", [])
            search_sites = kwargs.get("search_sites", [])

            # 获取过滤参数
            rule_groups = kwargs.get("rule_groups", [])
            quality = kwargs.get("quality")
            resolution = kwargs.get("resolution")
            effect = kwargs.get("effect")
            include = kwargs.get("include")
            exclude = kwargs.get("exclude")
            size = kwargs.get("size")
            prioritize_downloaded = kwargs.get("prioritize_downloaded", True)

            logger.info(f"开始订阅多版本过滤，订阅ID: {subscribe_ids}, 站点: {search_sites}")

            # 获取订阅信息
            if context.subscribes:
                # 从上下文中获取订阅
                subscribes = context.subscribes
            else:
                # 从数据库查询订阅
                if subscribe_ids:
                    subscribes = [self._subscribe_oper.get(sid) for sid in subscribe_ids if self._subscribe_oper.get(sid)]
                else:
                    subscribes = self._subscribe_oper.list()

            if not subscribes:
                logger.warning("未找到订阅信息")
                return True, context

            # 初始化结果
            all_torrents = []
            media_infos = []
            downloaded_episodes = {}  # 记录已下载的集数，按订阅ID分组

            # 处理每个订阅
            for subscribe in subscribes:
                try:
                    # 转换订阅为媒体信息
                    media_info = self._convert_subscribe_to_media_info(subscribe)
                    if not media_info:
                        logger.warning(f"订阅 {subscribe.name} 转换媒体信息失败，跳过处理")
                        continue

                    media_infos.append(media_info)

                    # 搜索站点种子（不包含已下载种子）
                    site_torrents = self._search_site_torrents(
                        media_info,
                        search_sites,
                        subscribe
                    )

                    # 获取该订阅的已下载种子
                    if prioritize_downloaded:
                        downloaded_torrents = self._get_downloaded_torrents_for_subscribe(subscribe, media_info)

                        # 先过滤已下载种子，只有符合规则的才参与去重
                        valid_downloaded_torrents = self._filter_torrents_with_rules(
                            downloaded_torrents,
                            media_info,
                            rule_groups=rule_groups,
                            quality=quality,
                            resolution=resolution,
                            effect=effect,
                            include=include,
                            exclude=exclude,
                            size=size,
                            downloaded_episodes=set(),  # 已下载种子之间不去重
                            prioritize_downloaded=False  # 已下载种子不做去重检查
                        )

                        # 只记录符合规则的已下载种子的集数
                        self._record_downloaded_episodes_for_subscribe(subscribe.id, valid_downloaded_torrents, downloaded_episodes)

                        # 将符合条件的已下载种子添加到总列表中
                        site_torrents.extend(valid_downloaded_torrents)

                    # 过滤种子
                    filtered_torrents = self._filter_torrents_with_rules(
                        site_torrents,
                        media_info,
                        rule_groups=rule_groups,
                        quality=quality,
                        resolution=resolution,
                        effect=effect,
                        include=include,
                        exclude=exclude,
                        size=size,
                        downloaded_episodes=downloaded_episodes.get(subscribe.id, set()),
                        prioritize_downloaded=prioritize_downloaded
                    )

                    all_torrents.extend(filtered_torrents)

                except Exception as e:
                    logger.error(f"处理订阅 {subscribe.name} 时出错: {str(e)}")
                    continue

            # 更新上下文
            context.torrents = all_torrents
            context.medias = media_infos
            context.content = f"订阅多版本过滤完成，共找到 {len(all_torrents)} 个种子资源"

            logger.info(f"订阅多版本过滤完成，共找到 {len(all_torrents)} 个种子")
            return True, context

        except Exception as e:
            logger.error(f"订阅多版本过滤失败: {str(e)}")
            return False, context

    def query_subscribe_torrents(self, context: ActionContext, **kwargs) -> Tuple[bool, ActionContext]:
        """
        查询订阅种子动作
        :param context: 工作流上下文
        :param kwargs: 动作参数
        :return: (执行状态, 更新后的上下文)
        """
        try:
            # 获取参数
            subscribe_ids = kwargs.get("subscribe_ids", [])
            search_sites = kwargs.get("search_sites", [])

            logger.info(f"开始查询订阅种子，订阅ID: {subscribe_ids}, 站点: {search_sites}")

            # 获取订阅信息
            if context.subscribes:
                # 从上下文中获取订阅
                subscribes = context.subscribes
            else:
                # 从数据库查询订阅
                if subscribe_ids:
                    subscribes = [self._subscribe_oper.get(sid) for sid in subscribe_ids if self._subscribe_oper.get(sid)]
                else:
                    subscribes = self._subscribe_oper.list()

            if not subscribes:
                logger.warning("未找到订阅信息")
                return True, context

            # 初始化结果
            all_torrents = []
            media_infos = []

            # 处理每个订阅
            for subscribe in subscribes:
                try:
                    # 转换订阅为媒体信息
                    media_info = self._convert_subscribe_to_media_info(subscribe)
                    if not media_info:
                        logger.warning(f"订阅 {subscribe.name} 转换媒体信息失败，跳过处理")
                        continue

                    media_infos.append(media_info)

                    # 搜索站点种子（不包含已下载种子）
                    site_torrents = self._search_site_torrents(
                        media_info,
                        search_sites,
                        subscribe
                    )
                    all_torrents.extend(site_torrents)

                except Exception as e:
                    logger.error(f"处理订阅 {subscribe.name} 时出错: {str(e)}")
                    continue

            # 更新上下文
            context.torrents = all_torrents
            context.medias = media_infos
            context.content = f"查询完成，共找到 {len(all_torrents)} 个种子资源"

            logger.info(f"查询订阅种子完成，共找到 {len(all_torrents)} 个种子")
            return True, context

        except Exception as e:
            logger.error(f"查询订阅种子失败: {str(e)}")
            return False, context

    def _convert_subscribe_to_media_info(self, subscribe: Subscribe) -> Optional[MediaInfo]:
        """
        将订阅对象转换为媒体信息对象
        :param subscribe: 订阅对象
        :return: 媒体信息对象
        """
        try:
            # 构建元数据对象
            meta = MetaInfo(subscribe.name)
            meta.year = subscribe.year
            meta.begin_season = subscribe.season or None
            meta.type = MediaType(subscribe.type)

            # 使用媒体识别链获取完整的媒体信息
            mediainfo: MediaInfo = self._media_chain.recognize_media(
                meta=meta,
                mtype=meta.type,
                tmdbid=subscribe.tmdbid,
                doubanid=subscribe.doubanid,
                bangumiid=subscribe.bangumiid,
                episode_group=subscribe.episode_group,
                cache=False
            )

            if not mediainfo:
                logger.warn(f'未识别到媒体信息，标题：{subscribe.name}，tmdbid：{subscribe.tmdbid}，doubanid：{subscribe.doubanid}')
                return None

            return mediainfo

        except ValueError as e:
            logger.error(f'订阅 {subscribe.name} 类型转换错误：{str(e)}')
            return None
        except Exception as e:
            logger.error(f'转换订阅 {subscribe.name} 到媒体信息失败：{str(e)}')
            return None

    def filter_torrents(self, context: ActionContext, **kwargs) -> Tuple[bool, ActionContext]:
        """
        过滤种子动作
        :param context: 工作流上下文
        :param kwargs: 动作参数
        :return: (执行状态, 更新后的上下文)
        """
        try:
            # 获取参数
            filter_rules = kwargs.get("filter_rules", self._default_filter_rules)
            prioritize_downloaded = kwargs.get("prioritize_downloaded", True)

            logger.info(f"开始过滤种子，规则: {filter_rules}")

            if not context.torrents and not context.subscribes:
                logger.warning("上下文中没有种子资源和订阅信息")
                return True, context

            # 解析过滤规则
            filter_params = self._parse_filter_rules(filter_rules)

            # 获取所有种子（包括已下载的种子）
            all_torrents = list(context.torrents or [])

            # 如果有订阅信息，查询已下载的种子
            if context.subscribes:
                downloaded_torrents = self._get_downloaded_torrents_from_subscribes(context.subscribes)
                # all_torrents.extend(downloaded_torrents)

            # 过滤种子
            filtered_torrents = []
            downloaded_episodes = set()  # 记录已下载的集数

            # 首先处理已下载的种子
            for torrent in downloaded_torrents:
                if torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:"):
                    # 检查已下载种子是否通过过滤
                    if self._check_torrent_filter(torrent, filter_params):
                        # 记录已下载的集数
                        self._record_downloaded_episodes(torrent, downloaded_episodes)
                        # filtered_torrents.append(torrent)

            # 处理搜索到的种子
            for torrent in all_torrents:
                if not (torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:")):
                    # 检查是否已经被已下载种子覆盖
                    if self._is_episode_covered(torrent, downloaded_episodes):
                        continue

                    # 应用过滤规则
                    if self._check_torrent_filter(torrent, filter_params):
                        filtered_torrents.append(torrent)

            # 更新上下文
            context.torrents = filtered_torrents
            context.content = f"过滤完成，共 {len(filtered_torrents)} 个种子通过过滤"

            # 如果有通过的种子，更新订阅状态
            if filtered_torrents and context.subscribes:
                self._update_subscribe_status(filtered_torrents, context.subscribes)

            logger.info(f"种子过滤完成，共 {len(filtered_torrents)} 个种子通过过滤")
            return True, context

        except Exception as e:
            logger.error(f"种子过滤失败: {str(e)}")
            return False, context

    def _get_downloaded_torrents_from_subscribes(self, subscribes: List[Subscribe]) -> List[Context]:
        """
        根据订阅列表获取已下载的种子
        """
        try:
            downloaded_torrents = []

            # 简化实现：从下载器获取已下载的种子
            # 由于下载器接口可能不同，这里只是一个示例实现
            try:
                # 使用DownloadChain获取下载器中的种子
                torrents = self._download_chain.get_downloading_torrents()

                for torrent in torrents:
                    # 检查种子是否匹配任何一个订阅
                    for subscribe in subscribes:
                        media_info = MediaInfo()
                        media_info.title = subscribe.name
                        media_info.year = subscribe.year
                        media_info.type = MediaType(subscribe.type)
                        media_info.tmdb_id = subscribe.tmdbid
                        media_info.season = subscribe.season
                        media_info.episode = subscribe.episode
                        media_info.total_episode = subscribe.total_episode

                        if self._match_torrent_to_subscribe(torrent, subscribe, media_info):
                            # 转换为Context对象
                            context_obj = Context()
                            context_obj.torrent_info = torrent
                            # 将下载信息存储在meta_info中
                            context_obj.meta_info = MetaInfo(title=torrent.title)
                            context_obj.meta_info.org_string = f"downloaded:unknown"
                            downloaded_torrents.append(context_obj)
                            break  # 匹配到一个订阅就停止

            except Exception as e:
                logger.error(f"获取已下载种子失败: {str(e)}")
                # 返回空列表而不是继续，避免错误传播

            logger.info(f"从下载器获取到 {len(downloaded_torrents)} 个已下载种子")
            return downloaded_torrents

        except Exception as e:
            logger.error(f"获取已下载种子失败: {str(e)}")
            return []

    def _search_site_torrents(self, media_info: MediaInfo, search_sites: List[str], subscribe: Subscribe) -> List[
        Context]:
        """
        搜索站点种子
        """
        try:
            site_torrents = []

            # 准备搜索参数（参考app/chain/search.py的__prepare_params方法）
            season_episodes, keywords = self._prepare_search_params(media_info)

            # 构建搜索参数
            search_params = {
                "keywords": keywords,
                "media_type": media_info.type.value,
                "season_episodes": season_episodes,
                "year": media_info.year,
                "sites": search_sites if search_sites else None
            }



            # 执行搜索（支持多个关键词）
            search_results = []
            for keyword in search_params["keywords"]:
                results = self._search_chain.search_by_title(
                    keyword,
                    sites=search_params["sites"]
                )
                search_results.extend(results)

            for result in search_results:
                try:
                    # 转换为Context对象
                    result.context = {
                        "downloaded": False,
                        "site": result.torrent_info.site_name,
                        "search_time": datetime.now().isoformat(),
                        "subscribe_id": subscribe.id
                    }
                    site_torrents.append(result)

                except Exception as e:
                    logger.error(f"处理搜索结果失败: {str(e)}")
                    continue

            logger.info(f"从站点搜索到 {len(site_torrents)} 个种子")
            return site_torrents

        except Exception as e:
            logger.error(f"搜索站点种子失败: {str(e)}")
            return []

    def _prepare_search_params(self, mediainfo: MediaInfo) -> Tuple[Dict[int, List[int]], List[str]]:
        """
        准备搜索参数（参考app/chain/search.py的__prepare_params方法）
        """
        from app.core.config import settings

        # 缺失的季集（这里简化处理，如果没有no_exists参数则使用当前季）
        if mediainfo.season:
            season_episodes = {mediainfo.season: []}
        else:
            season_episodes = None

        # 搜索关键词（去重去空，保持顺序）
        keywords = list(dict.fromkeys([
            k for k in [
                mediainfo.title,
                mediainfo.original_title,
                mediainfo.en_title,
                mediainfo.hk_title,
                mediainfo.tw_title,
                mediainfo.sg_title
            ] if k
        ]))

        # 限制搜索关键词数量
        if hasattr(settings, 'MAX_SEARCH_NAME_LIMIT') and settings.MAX_SEARCH_NAME_LIMIT:
            keywords = keywords[:settings.MAX_SEARCH_NAME_LIMIT]

        return season_episodes, keywords

    def _match_torrent_to_subscribe(self, torrent, subscribe: Subscribe, media_info: MediaInfo) -> bool:
        """
        检查种子是否匹配订阅
        """
        try:
            # 简单的标题匹配逻辑
            torrent_title = torrent.title.lower()
            subscribe_title = media_info.title.lower()

            # 检查标题是否包含
            if subscribe_title not in torrent_title:
                return False

            # 检查年份
            if media_info.year and str(media_info.year) not in torrent_title:
                return False

            # 检查季集信息
            if media_info.type == MediaType.TV:
                if media_info.season:
                    season_str = f"s{media_info.season:02d}"
                    if season_str not in torrent_title.lower():
                        return False

                if media_info.episode:
                    episode_str = f"e{media_info.episode:02d}"
                    if episode_str not in torrent_title.lower():
                        return False

            return True

        except Exception as e:
            logger.error(f"匹配种子到订阅失败: {str(e)}")
            return False

    def _parse_filter_rules(self, rules_str: str) -> Dict[str, Any]:
        """
        解析过滤规则
        """
        try:
            if not rules_str:
                return {}

            # 简单的JSON解析
            try:
                return json.loads(rules_str)
            except json.JSONDecodeError:
                # 如果不是JSON，尝试解析键值对
                rules = {}
                for rule in rules_str.split(","):
                    if "=" in rule:
                        key, value = rule.split("=", 1)
                        rules[key.strip()] = value.strip()
                return rules

        except Exception as e:
            logger.error(f"解析过滤规则失败: {str(e)}")
            return {}

    def _check_torrent_filter(self, torrent: Context, filter_params: Dict[str, Any]) -> bool:
        """
        检查种子是否通过过滤
        """
        try:
            # 使用MoviePilot的过滤模块
            if not filter_params:
                return True

            # 调用过滤模块
            filtered_torrents = self._filter_module.filter_torrents(
                filter_params.get("rule_groups", []),
                [torrent.torrent_info],
                torrent.media_info
            )
            return len(filtered_torrents) > 0

        except Exception as e:
            logger.error(f"检查种子过滤失败: {str(e)}")
            return False

    def _record_downloaded_episodes(self, torrent: Context, downloaded_episodes: set):
        """
        记录已下载的集数
        """
        try:
            media_info = torrent.media_info
            if media_info and media_info.type == MediaType.TV:
                if media_info.episode:
                    downloaded_episodes.add(media_info.episode)
                elif media_info.season:
                    # 整季下载
                    downloaded_episodes.add(f"s{media_info.season}")

        except Exception as e:
            logger.error(f"记录已下载集数失败: {str(e)}")

    def _is_episode_covered(self, torrent: Context, downloaded_episodes: set) -> bool:
        """
        检查集数是否已被覆盖
        """
        try:
            media_info = torrent.media_info
            if not media_info or media_info.type != MediaType.TV:
                return False

            if media_info.episode:
                return media_info.episode in downloaded_episodes
            elif media_info.season:
                return f"s{media_info.season}" in downloaded_episodes

            return False

        except Exception as e:
            logger.error(f"检查集数覆盖失败: {str(e)}")
            return False

    def _update_subscribe_status(self, filtered_torrents: List[Context], subscribes: List[Subscribe]):
        """
        更新订阅状态
        """
        try:
            # 更新订阅状态逻辑
            for torrent in filtered_torrents:
                if torrent.meta_info and torrent.meta_info.org_string and torrent.meta_info.org_string.startswith(
                        "downloaded:"):
                    # 已下载种子通过过滤，更新对应订阅状态
                    # 这里需要从org_string中解析subscribe_id，或者使用其他方式存储
                    # 由于当前实现没有存储subscribe_id，这里只是示例
                    self.post_message(
                        title="订阅状态更新",
                        text=f"已下载种子通过过滤检查"
                    )

        except Exception as e:
            logger.error(f"更新订阅状态失败: {str(e)}")

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enable_search',
                                            'label': '启用查询功能',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enable_filter',
                                            'label': '启用过滤功能',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'default_filter_rules',
                                            'label': '默认过滤规则',
                                            'placeholder': '默认的过滤规则，JSON格式或键值对格式',
                                            'rows': 4,
                                            'hint': '默认的过滤规则，JSON格式或键值对格式',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '订阅多资源版本订阅插件提供基于订阅的多资源版本管理和过滤功能。'
                                                    '启用查询功能后，插件会根据订阅信息查询种子资源。'
                                                    '启用过滤功能后，插件会根据设定的规则过滤种子资源。'
                                                    '过滤规则支持JSON格式或键值对格式。'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "enable_search": True,
            "enable_filter": True,
            "default_filter_rules": ""
        }

    def get_page(self) -> List[dict]:
        """
        获取插件页面
        """
        pass

    def stop_service(self):
        """
        停止插件服务
        """
        pass

    def _get_downloaded_torrents_for_subscribe(self, subscribe: Subscribe, media_info: MediaInfo) -> List[Context]:
        """
        根据订阅获取已下载的种子
        """
        try:
            downloaded_torrents = []

            # 使用下载历史获取已下载的种子
            try:
                # 查询该订阅的下载历史
                if media_info.tmdb_id:
                    download_history = self._download_history_oper.get_by_mediaid(
                        tmdbid=media_info.tmdb_id,
                        doubanid=media_info.douban_id or ""
                    )
                else:
                    download_history = []

                for history in download_history:
                    # 转换为Context对象
                    context_obj = Context()
                    # 创建TorrentInfo对象
                    torrent_info = TorrentInfo(
                        title=history.torrent_name or "",
                        site=history.torrent_site or "",
                        description=history.torrent_description or "",
                        size=0  # 下载历史中没有大小信息
                    )
                    context_obj.torrent_info = torrent_info
                    context_obj.media_info = media_info
                    # 将下载信息存储在meta_info中
                    context_obj.meta_info = MetaInfo(title=history.torrent_name or "")
                    context_obj.meta_info.org_string = f"downloaded:{subscribe.id}"
                    downloaded_torrents.append(context_obj)

            except Exception as e:
                logger.error(f"获取已下载种子失败: {str(e)}")

            logger.info(f"从下载历史获取到 {len(downloaded_torrents)} 个已下载种子")
            return downloaded_torrents

        except Exception as e:
            logger.error(f"获取已下载种子失败: {str(e)}")
            return []

    def _record_downloaded_episodes_for_subscribe(self, subscribe_id: int, downloaded_torrents: List[Context], downloaded_episodes: dict):
        """
        记录已下载的集数（按订阅ID分组）
        """
        try:
            if subscribe_id not in downloaded_episodes:
                downloaded_episodes[subscribe_id] = set()

            for torrent in downloaded_torrents:
                meta_info = torrent.meta_info
                if not meta_info:
                    continue

                # 从种子的meta_info中获取集数信息
                if meta_info.episode_list:
                    # 多集种子：记录每一集
                    for episode in meta_info.episode_list:
                        downloaded_episodes[subscribe_id].add(episode)
                elif meta_info.begin_episode:
                    # 单集种子：记录开始集
                    if meta_info.end_episode:
                        # 如果有结束集，记录范围内的所有集
                        for episode in range(meta_info.begin_episode, meta_info.end_episode + 1):
                            downloaded_episodes[subscribe_id].add(episode)
                    else:
                        # 只有开始集
                        downloaded_episodes[subscribe_id].add(meta_info.begin_episode)
                elif meta_info.season:
                    # 整季种子：episode_list为空代表整季都包含
                    downloaded_episodes[subscribe_id].add(f"s{meta_info.season}")

        except Exception as e:
            logger.error(f"记录已下载集数失败: {str(e)}")

    def _filter_torrents_with_rules(self, torrents: List[Context], media_info: MediaInfo,
                                  rule_groups: List[str] = None, quality: str = None,
                                  resolution: str = None, effect: str = None, include: str = None,
                                  exclude: str = None, size: str = None,
                                  downloaded_episodes: set = None, prioritize_downloaded: bool = True) -> List[Context]:
        """
        使用规则过滤种子
        """
        try:
            filtered_torrents = []

            if downloaded_episodes is None:
                downloaded_episodes = set()

            # 构建过滤参数
            filter_params = {
                "quality": quality,
                "resolution": resolution,
                "effect": effect,
                "include": include,
                "exclude": exclude,
                "size": size
            }

            for torrent in torrents:
                try:
                    # 检查是否是已下载种子
                    is_downloaded = (torrent.meta_info and torrent.meta_info.org_string and
                                  torrent.meta_info.org_string.startswith("downloaded:"))

                    # 如果是已下载种子，检查是否通过过滤
                    if is_downloaded:
                        if self._check_torrent_filter(torrent, filter_params):
                            # 已下载种子通过过滤，保留
                            filtered_torrents.append(torrent)
                        continue

                    # 如果不是已下载种子，检查是否完全被已下载种子覆盖
                    if prioritize_downloaded and self._is_episode_covered_for_media(torrent, media_info, downloaded_episodes):
                        # 该种子的所有集数都已经被下载，跳过
                        continue

                    # 应用基本过滤规则
                    if not TorrentHelper.filter_torrent(torrent.torrent_info, filter_params):
                        continue

                    # 应用规则组过滤
                    if rule_groups:
                        filtered_by_rules = self._filter_module.filter_torrents(
                            rule_groups,
                            [torrent.torrent_info],
                            media_info
                        )
                        if not filtered_by_rules:
                            continue

                    # 通过所有过滤，保留种子
                    filtered_torrents.append(torrent)

                except Exception as e:
                    logger.error(f"过滤种子时出错: {str(e)}")
                    continue

            return filtered_torrents

        except Exception as e:
            logger.error(f"过滤种子失败: {str(e)}")
            return []

    def _is_episode_covered_for_media(self, torrent: Context, media_info: MediaInfo, downloaded_episodes: set) -> bool:
        """
        检查种子是否完全被已下载集数覆盖
        只有当种子的所有集数都已经被下载时，才返回True进行过滤
        """
        try:
            torrent_info = torrent.torrent_info
            if not torrent_info or not media_info or media_info.type != MediaType.TV:
                return False

            # 从种子标题中解析集数信息
            meta_info = MetaInfo(torrent_info.title)

            # 如果是整季种子
            if not meta_info.episode_list and meta_info.season:
                # 检查是否该整季已经下载
                season_key = f"s{meta_info.season}"
                return season_key in downloaded_episodes

            # 如果是多集种子
            elif meta_info.episode_list:
                # 检查是否所有集都已经被下载
                for episode in meta_info.episode_list:
                    if episode not in downloaded_episodes:
                        return False
                return True

            # 如果是单集种子
            elif meta_info.begin_episode:
                return meta_info.begin_episode in downloaded_episodes

            return False

        except Exception as e:
            logger.error(f"检查集数覆盖失败: {str(e)}")
            return False
