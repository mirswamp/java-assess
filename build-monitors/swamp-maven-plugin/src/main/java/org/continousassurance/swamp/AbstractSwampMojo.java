package org.continousassurance.swamp;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

import org.apache.commons.io.FilenameUtils;
import org.apache.maven.artifact.DependencyResolutionRequiredException;
import org.apache.maven.model.Plugin;
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.project.MavenProject;
import org.codehaus.plexus.util.FileUtils;
import org.codehaus.plexus.util.xml.Xpp3Dom;
import org.codehaus.plexus.util.xml.Xpp3DomBuilder;
import org.codehaus.plexus.util.xml.Xpp3DomWriter;
import org.codehaus.plexus.util.xml.pull.XmlPullParserException;

public abstract class AbstractSwampMojo extends AbstractMojo {
	
	/** XML element name for a build. */
	static final String BUILD_TAG = "build-artifacts";
	static final String JAVA_COMPILE_TAG = "java-compile";
	static final String SRCDIR_TAG = "srcdir";
	static final String SRCFILE_TAG = "srcfile";
	static final String DESTDIR_TAG = "destdir";
	static final String INCLUDE_TAG = "include";
	static final String EXCLUDE_TAG = "exclude";
	static final String SOURCE_TAG = "source";
	static final String TARGET_TAG = "target";
	static final String ENCODING_TAG = "encoding";
	static final String CLASSPATH_TAG = "classpath";
	static final String BOOTCLASSPATH_TAG = "bootclasspath";
	static final String SOURCEPATH_TAG = "sourcepath";

	static final String FILE_TAG = "file";
	static final String PATTERN_TAG = "pattern";

	static final String ALL_JAVA_PATTERN = "**/*.java";
	
	private static int buildArtifactsCount = 0;
	
	protected void writeArtifacts(Xpp3Dom root_element) throws MojoExecutionException{
		if(root_element.getChildCount() > 0) {
			File build_monitor_output_file = getBuildMonitorOutputFile();
			if(build_monitor_output_file.exists() && build_monitor_output_file.isFile()) { 
				try {
					FileReader file_reader = new FileReader(build_monitor_output_file);
					Xpp3Dom existing_artifacts = Xpp3DomBuilder.build(file_reader);
					for(Xpp3Dom artifact: existing_artifacts.getChildren()) {
						root_element.addChild(artifact);
					}
					file_reader.close();
				} catch (FileNotFoundException e) {
					e.printStackTrace();
				} catch (XmlPullParserException e) {
					e.printStackTrace();
				} catch (IOException e) {
					e.printStackTrace();
				}
			}

			String xslUri = getProject().getProperties().getProperty("ant.XmlLogger.stylesheet.uri");
			if (xslUri == null) {
				xslUri = "log.xsl";
			}

			PrintWriter out = null;
			try {
				// specify output in UTF8 otherwise accented characters will blow
				// up everything
				out = new PrintWriter(build_monitor_output_file, "UTF8");
				out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
				if (xslUri.length() > 0) {
					out.write("<?xml-stylesheet type=\"text/xsl\" href=\"" + xslUri + "\"?>\n\n");
				}
				Xpp3DomWriter.write(out, root_element);
				out.flush();
			} catch (IOException exc) {
				throw new MojoExecutionException("Unable to write to " + build_monitor_output_file.getAbsolutePath());
			} finally {
				if (out != null){
					out.close();
				}
			}
		}
	}

	protected void addXmlElement(String tag, String text, Xpp3Dom parent) {
		Xpp3Dom elem = new Xpp3Dom(tag);
		elem.setValue(text);
		parent.addChild(elem);
	}

	protected Xpp3Dom[] getFileFilters(MavenProject project, String filter_name){
		Xpp3Dom[] file_filters = null;

		for(Plugin p : (List<Plugin>)(List<?>)project.getBuildPlugins()) {
			if(p.getKey().compareToIgnoreCase("org.apache.maven.plugins:maven-compiler-plugin") == 0){
				if(p.getConfiguration() != null &&
						p.getConfiguration() instanceof org.codehaus.plexus.util.xml.Xpp3Dom) {

					for(Xpp3Dom child : ((org.codehaus.plexus.util.xml.Xpp3Dom)p.getConfiguration()).getChildren()) {
						if(child.getName().compareToIgnoreCase(filter_name) == 0) {
							file_filters = child.getChildren();
						}
					}
				}
			}
		}
		return file_filters;
	}
	
	protected List<String> getFileFilters(MavenProject project, String filter_name, String default_value){
		List<String> file_filters = new ArrayList<String>();

		for(Plugin p : (List<Plugin>)(List<?>)project.getBuildPlugins()) {
			if(p.getKey().compareToIgnoreCase("org.apache.maven.plugins:maven-compiler-plugin") == 0){
				if(p.getConfiguration() != null &&
						p.getConfiguration() instanceof org.codehaus.plexus.util.xml.Xpp3Dom) {

					for(Xpp3Dom config_child : ((org.codehaus.plexus.util.xml.Xpp3Dom)p.getConfiguration()).getChildren()) {
						if(config_child.getName().compareToIgnoreCase(filter_name) == 0) {
							for (Xpp3Dom filter : config_child.getChildren()) {
								file_filters.add(filter.getValue());
							}
						}
					}
				}
			}
		}
		
		if (file_filters.isEmpty()){
			file_filters.add(default_value);
		}
		
		return file_filters;
	}
	
	protected Collection<? extends File> getStaleFiles(List<File> fileList, File srcDir, File destDir) {

		List<File> new_file_list = new ArrayList<File>();

		for (File src_file : fileList){
			String pkg_path = src_file.getPath().substring(srcDir.getPath().length() + 1);
			File class_file = new File(FilenameUtils.concat(destDir.getPath(), FilenameUtils.removeExtension(pkg_path)) + ".class");

			if (class_file.exists()){
				if (src_file.lastModified() > class_file.lastModified()){
					new_file_list.add(src_file);
				}
			}else {
				new_file_list.add(src_file);
			}
		}

		return new_file_list;
	}
	
	protected String getPluginParameter(String plugin_key, //groupId:artifactId
			String plugin_param_name,
			String plugin_param_property,
			String plugin_param_default_value) {
		String plugin_param_str = null;

		for(Plugin p : (List<Plugin>)(List<?>)getProject().getBuildPlugins()) {
			if(p.getKey().compareToIgnoreCase(plugin_key) == 0){

				if(p.getConfiguration() != null &&
					p.getConfiguration() instanceof org.codehaus.plexus.util.xml.Xpp3Dom) {
						org.codehaus.plexus.util.xml.Xpp3Dom config = (org.codehaus.plexus.util.xml.Xpp3Dom)p.getConfiguration();
						if(config.getChildCount() > 0) {
							for(Xpp3Dom child : config.getChildren()) {
								if(child.getName().compareToIgnoreCase(plugin_param_name) == 0) {
									plugin_param_str = child.getValue();
									break;
								}
							}
						}
					
				}
			}
		}			

		if((plugin_param_str == null) && (plugin_param_property != null)) {
			Properties all_props = getProject().getProperties();
			plugin_param_str = all_props.getProperty(plugin_param_property,
								 plugin_param_default_value);
		}

		return plugin_param_str;
	}
	
	protected abstract MavenProject getProject();
	protected abstract File getBuildMonitorOutputFile();
	protected abstract boolean skipCompile();	
	protected abstract File getGeneratedSourcesDirectory();
	protected abstract List<File> getSourceDirectories();
	protected abstract List<String> getIncludeFileFilters();
	protected abstract List<String> getExcludeFileFilters();
	protected abstract File getOutputDirectory();
	protected abstract String getSourceVersion();
	protected abstract String getTargetVersion();
	protected abstract List<String> getClasspathFiles() throws DependencyResolutionRequiredException;
	
	protected List<File> getSourceFiles(List<File> srcDirs, 
			List<String> includeFileFilters, 
			List<String> excludeFileFilters,
			File outDir) {
		
		List<File> src_files = new ArrayList<File>();

		for(File src_dir : srcDirs) {			
			for (String infilter : includeFileFilters) {
				for (String exfilter : excludeFileFilters) {
					try {
						src_files.addAll(getStaleFiles(FileUtils.getFiles(src_dir, infilter, exfilter),
								src_dir,
								outDir));

					} catch (IOException e) {
						e.printStackTrace();
					}
				}
			}
		}

		return src_files;		
	}

	protected String getSourceEncoding() {		
		return getPluginParameter("org.apache.maven.plugins:maven-compiler-plugin",
				"encoding", 
				"project.build.sourceEncoding", 
				System.getProperty("file.encoding", null));	
	}

	protected Xpp3Dom getJavaCompile() {

		if(skipCompile()) {
			return null;
		}

		List<File> src_dirs = getSourceDirectories();

		if (src_dirs.isEmpty()){
			return null;
		}
		
		List<String> include_filters = getIncludeFileFilters();
		List<String> exclude_filters = getExcludeFileFilters();
		File out_dir = getOutputDirectory();
		
		List<File> test_src_files = getSourceFiles(src_dirs, include_filters, exclude_filters, out_dir);
		if (test_src_files.isEmpty()) {
			return null;
		}
		
		Xpp3Dom java_compile_tag = new Xpp3Dom(AbstractSwampMojo.JAVA_COMPILE_TAG);
		java_compile_tag.setAttribute("id", Integer.toString(++buildArtifactsCount));

		Xpp3Dom src_dir_tag = new Xpp3Dom(AbstractSwampMojo.SRCDIR_TAG);
		Xpp3Dom src_file_tag = new Xpp3Dom(AbstractSwampMojo.SRCFILE_TAG);

		for(File src_dir : src_dirs){
			addXmlElement(AbstractSwampMojo.FILE_TAG, src_dir.getAbsolutePath(), src_dir_tag);
		}
		java_compile_tag.addChild(src_dir_tag);

		for (File srcfile : test_src_files) {
			addXmlElement(AbstractSwampMojo.FILE_TAG, srcfile.getAbsolutePath(), src_file_tag);
		}
		java_compile_tag.addChild(src_file_tag);
		
		if(out_dir != null) {
            Xpp3Dom destdir_tag = new Xpp3Dom(AbstractSwampMojo.DESTDIR_TAG);
            addXmlElement(AbstractSwampMojo.FILE_TAG, out_dir.getAbsolutePath(), destdir_tag);
            java_compile_tag.addChild(destdir_tag);
    }
		
		Xpp3Dom include_tag = new Xpp3Dom(AbstractSwampMojo.INCLUDE_TAG);
		for(String filter : include_filters) {
			if (filter.length() > 0) {
				addXmlElement(AbstractSwampMojo.PATTERN_TAG, filter, include_tag);
			}
		}
		if (include_tag.getChildCount() > 0){
			java_compile_tag.addChild(include_tag);
		}
		
		Xpp3Dom exclude_tag = new Xpp3Dom(AbstractSwampMojo.EXCLUDE_TAG);
		for(String filter : exclude_filters) {
			if (filter.length() > 0) {
				addXmlElement(AbstractSwampMojo.PATTERN_TAG, filter, exclude_tag);
			}
		}
		if (exclude_tag.getChildCount() > 0){
			java_compile_tag.addChild(exclude_tag);
		}
		
		String source_version = getSourceVersion();
		if (source_version != null) {
			addXmlElement(AbstractSwampMojo.SOURCE_TAG, source_version, java_compile_tag);
		}
		
		String target_version = getTargetVersion();
		if (target_version != null) {
			addXmlElement(AbstractSwampMojo.TARGET_TAG, target_version, java_compile_tag);
		}
		
		String encoding = getSourceEncoding();
		if (encoding != null) {
			addXmlElement(AbstractSwampMojo.ENCODING_TAG, encoding, java_compile_tag);
		}
		try {
			List<String> classpath = getClasspathFiles();
		
			if(classpath != null){
				Xpp3Dom classpath_tag = new Xpp3Dom(AbstractSwampMojo.CLASSPATH_TAG);
				for(String str : classpath){
					addXmlElement(AbstractSwampMojo.FILE_TAG, str, classpath_tag); 
				}

				if (classpath_tag.getChildCount() > 0){
					java_compile_tag.addChild(classpath_tag);
				}
			}
		}catch (DependencyResolutionRequiredException exception) {
			System.err.println(exception);
			System.exit(1);
		}

		return java_compile_tag;   	
	}

	protected void executeSingle() throws MojoExecutionException {

		Xpp3Dom root_element = new Xpp3Dom(BUILD_TAG);
		root_element.setAttribute("id", UUID.randomUUID().toString());

		Xpp3Dom test_element = getJavaCompile();
		if(test_element != null){
			root_element.addChild(test_element);
		}

		if(root_element.getChildCount() > 0) {
			writeArtifacts(root_element);
		}
	}

	public void execute() throws MojoExecutionException {

		if(getProject().isExecutionRoot()){
			if((getProject().getModules().size() == 0) || (getProject().getPackaging().compareToIgnoreCase("pom") != 0)){
				executeSingle();
			}
		}else {    		
			executeSingle();
		}
	}

}
